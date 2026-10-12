// fcvr - shows the model you are editing in FreeCAD floating in VR, next to your desktop windows.
//
// It is a SteamVR *overlay* (like the desktop panels), not a scene app, so the desktop stays.
// The overlay is a transparent side-by-side stereo sheet at the model's depth that covers only the part of
// the model inside your field of view (so zooming in keeps full resolution) and faces
// you; each half is rendered from that eye's tracked position, so the model has real depth.
//
// Input files in ~/.vr-model-viewer (written by FreeCAD's VRLiveExport add-on), or in --dir DIR
// (optiland_ui's VR view writes the same files there and passes --parent-pid):
//   model.bin  the visible shapes (reloaded when it changes, format in vr_live_export.py)
//   view       FreeCAD camera rotation; in follow mode the model turns with the FreeCAD view
//   cmd        "<seq> <command>" from the FreeCAD hotkeys:
//              real (1:1), big (~1.2 m), fit (~35 cm), bigger, smaller, recenter, follow (toggle),
//              scale <n> (n x real size), zoom <f> (multiply the size by f)
// Controllers (actions.json / bindings_frame_controller.json): grip = grab and move, both grips = stretch
// to scale, grip + thumbstick up/down = scale. The trigger is left alone for the desktop panels.
// The model starts at real size.
#define GL_GLEXT_PROTOTYPES
#include <EGL/egl.h>
#include <GL/gl.h>
#include <GL/glext.h>
#include <openvr/openvr_capi.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <dirent.h>
#include <strings.h>

extern intptr_t VR_InitInternal(EVRInitError *peError, EVRApplicationType eType);
extern void VR_ShutdownInternal(void);
extern intptr_t VR_GetGenericInterface(const char *pchInterfaceVersion, EVRInitError *peError);

static volatile int g_quit;
static void on_sig(int s) { (void)s; g_quit = 1; }

#define EYE_PX 2560        // largest per-eye render; frames render at ~2 px per headset pixel, up to this
#define MSAA 4

/* ---------- tiny math ---------- */
typedef struct { float x, y, z; } V3;
typedef struct { float x, y, z, w; } Q;
static V3 v3(float x, float y, float z) { V3 v = {x, y, z}; return v; }
static V3 vadd(V3 a, V3 b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
static V3 vsub(V3 a, V3 b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
static V3 vmul(V3 a, float s) { return v3(a.x * s, a.y * s, a.z * s); }
static float vdot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static V3 vcross(V3 a, V3 b) { return v3(a.y*b.z - a.z*b.y, a.z*b.x - a.x*b.z, a.x*b.y - a.y*b.x); }
static float vlen(V3 a) { return sqrtf(vdot(a, a)); }
static V3 vnorm(V3 a) { float l = vlen(a); return l > 0 ? vmul(a, 1 / l) : a; }
static Q qmul(Q a, Q b) {
    Q r = {a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y, a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
           a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w, a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z};
    return r;
}
static Q qinv(Q a) { Q r = {-a.x, -a.y, -a.z, a.w}; return r; }
static V3 qrot(Q q, V3 v) { Q p = {v.x, v.y, v.z, 0}; Q r = qmul(qmul(q, p), qinv(q)); return v3(r.x, r.y, r.z); }
static Q qaxis(V3 ax, float a) { Q r = {ax.x * sinf(a / 2), ax.y * sinf(a / 2), ax.z * sinf(a / 2), cosf(a / 2)}; return r; }

typedef struct { float m[16]; } M4; // column-major
static M4 m_ident(void) { M4 r = {{1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1}}; return r; }
static M4 m_from(Q q, V3 p, float s) {
    float x = q.x, y = q.y, z = q.z, w = q.w; M4 r;
    r.m[0] = (1 - 2*(y*y + z*z)) * s; r.m[1] = 2*(x*y + z*w) * s;      r.m[2] = 2*(x*z - y*w) * s;      r.m[3] = 0;
    r.m[4] = 2*(x*y - z*w) * s;      r.m[5] = (1 - 2*(x*x + z*z)) * s; r.m[6] = 2*(y*z + x*w) * s;      r.m[7] = 0;
    r.m[8] = 2*(x*z + y*w) * s;      r.m[9] = 2*(y*z - x*w) * s;      r.m[10] = (1 - 2*(x*x + y*y)) * s; r.m[11] = 0;
    r.m[12] = p.x; r.m[13] = p.y; r.m[14] = p.z; r.m[15] = 1;
    return r;
}
static M4 mmul(M4 a, M4 b) {
    M4 r;
    for (int c = 0; c < 4; c++) for (int rr = 0; rr < 4; rr++) {
        float s = 0; for (int k = 0; k < 4; k++) s += a.m[k*4 + rr] * b.m[c*4 + k]; r.m[c*4 + rr] = s;
    }
    return r;
}
static V3 m34_pos(HmdMatrix34_t m) { return v3(m.m[0][3], m.m[1][3], m.m[2][3]); }
static V3 m34_apply(HmdMatrix34_t m, V3 p) {
    return v3(m.m[0][0]*p.x + m.m[0][1]*p.y + m.m[0][2]*p.z + m.m[0][3],
              m.m[1][0]*p.x + m.m[1][1]*p.y + m.m[1][2]*p.z + m.m[1][3],
              m.m[2][0]*p.x + m.m[2][1]*p.y + m.m[2][2]*p.z + m.m[2][3]);
}

// Off-axis projection*view for an eye at e looking through the rectangle (centre c, unit right R, up U, size w x h).
static M4 window_mvp(V3 e, V3 c, V3 R, V3 U, float w, float h, float n, float f) {
    V3 N = vcross(R, U);                                   // towards the viewer
    V3 pa = vsub(vsub(c, vmul(R, w / 2)), vmul(U, h / 2));
    V3 pb = vadd(pa, vmul(R, w)), pc = vadd(pa, vmul(U, h));
    V3 va = vsub(pa, e), vb = vsub(pb, e), vc = vsub(pc, e);
    float d = -vdot(va, N); if (d < 1e-3f) d = 1e-3f;
    float l = vdot(R, va) * n / d, r = vdot(R, vb) * n / d, b = vdot(U, va) * n / d, t = vdot(U, vc) * n / d;
    M4 P = {{0}};
    P.m[0] = 2*n / (r - l); P.m[5] = 2*n / (t - b); P.m[8] = (r + l) / (r - l); P.m[9] = (t + b) / (t - b);
    P.m[10] = -(f + n) / (f - n); P.m[11] = -1; P.m[14] = -2*f*n / (f - n);
    M4 Mt = m_ident();                                      // rows R, U, N
    Mt.m[0] = R.x; Mt.m[4] = R.y; Mt.m[8] = R.z;
    Mt.m[1] = U.x; Mt.m[5] = U.y; Mt.m[9] = U.z;
    Mt.m[2] = N.x; Mt.m[6] = N.y; Mt.m[10] = N.z;
    M4 T = m_ident(); T.m[12] = -e.x; T.m[13] = -e.y; T.m[14] = -e.z;
    return mmul(P, mmul(Mt, T));
}

/* ---------- model ---------- */
// Faces: pos, normal, diffuse rgb, ambient rgb, specular rgb, shininess  (16 floats)
// Edges: this end, other end, side (+-1), rgb, width px                  (11 floats, 6 verts per segment)
static GLuint vao_t, vbo_t, vao_l, vbo_l;
static int n_tv, n_lv, n_hv;          // hatch lines follow the n_lv others in the same buffer
static float hatch_step;              // metres between hatch lines (model scale 1), 0 = none
static V3 m_center, m_lo, m_hi; static float m_size = 0.1f; // metres, Y-up
static int have_model;

static int load_model(const char *path) {
    FILE *f = fopen(path, "rb"); if (!f) return 0;
    fseek(f, 0, SEEK_END); long len = ftell(f); fseek(f, 0, SEEK_SET);
    unsigned char *buf = malloc(len > 0 ? len : 1);
    uint32_t ver = 0;
    int ok = len >= 12 && fread(buf, 1, len, f) == (size_t)len && !memcmp(buf, "VRMV", 4);
    fclose(f);
    if (ok) memcpy(&ver, buf + 4, 4);
    if (!ok || ver != 2) { free(buf); return 0; }
    uint32_t nobj; memcpy(&nobj, buf + 8, 4);
    size_t off = 12, ttot = 0, ltot = 0;
    for (uint32_t o = 0; o < nobj; o++) {                     // validate + count
        uint32_t c[3]; if (off + 76 > (size_t)len) { free(buf); return 0; }
        memcpy(c, buf + off + 64, 12);
        off += 76 + (size_t)c[0] * 12 + (size_t)c[1] * 12 + (size_t)c[2] * 12; ttot += c[1]; ltot += c[2] / 2;
        if (off > (size_t)len) { free(buf); return 0; }
    }
    float *tout = malloc(ttot * 3 * 64 + 64), *w = tout;
    float *lout = malloc(ltot * 6 * 44 + 44), *lw = lout;
    float *hout = malloc(ltot * 6 * 44 + 44), *hw_ = hout;
    hatch_step = 0;
    V3 lo = v3(1e30f, 1e30f, 1e30f), hi = v3(-1e30f, -1e30f, -1e30f);
    #define CONV(P) do { float x_ = (P)[0], y_ = (P)[1], z_ = (P)[2]; \
        (P)[0] = x_ * 0.001f; (P)[1] = z_ * 0.001f; (P)[2] = -y_ * 0.001f; \
        lo.x = fminf(lo.x, (P)[0]); lo.y = fminf(lo.y, (P)[1]); lo.z = fminf(lo.z, (P)[2]); \
        hi.x = fmaxf(hi.x, (P)[0]); hi.y = fmaxf(hi.y, (P)[1]); hi.z = fmaxf(hi.z, (P)[2]); } while (0)
    off = 12;
    for (uint32_t o = 0; o < nobj; o++) {
        float mat[16]; uint32_t c[3];
        memcpy(mat, buf + off, 64); memcpy(c, buf + off + 64, 12);
        uint32_t nv = c[0], nt = c[1], nl = c[2];
        float *P = malloc((size_t)nv * 12 + 12); memcpy(P, buf + off + 76, (size_t)nv * 12);
        uint32_t *T = malloc((size_t)nt * 12 + 12); memcpy(T, buf + off + 76 + (size_t)nv * 12, (size_t)nt * 12);
        float *L = malloc((size_t)nl * 12 + 12); memcpy(L, buf + off + 76 + (size_t)nv * 12 + (size_t)nt * 12, (size_t)nl * 12);
        off += 76 + (size_t)nv * 12 + (size_t)nt * 12 + (size_t)nl * 12;
        for (uint32_t i = 0; i < nv; i++) CONV(P + i*3);
        for (uint32_t i = 0; i < nl; i++) CONV(L + i*3);
        // smooth vertex normals (vertices are per face, so face boundaries stay sharp like in FreeCAD)
        V3 *VN = calloc(nv + 1, sizeof(V3));
        for (uint32_t t = 0; t < nt; t++) {
            uint32_t *tr = T + t*3;
            if (tr[0] >= nv || tr[1] >= nv || tr[2] >= nv) { tr[0] = tr[1] = tr[2] = 0; continue; }
            V3 a = v3(P[tr[0]*3], P[tr[0]*3+1], P[tr[0]*3+2]), b = v3(P[tr[1]*3], P[tr[1]*3+1], P[tr[1]*3+2]),
               cc = v3(P[tr[2]*3], P[tr[2]*3+1], P[tr[2]*3+2]);
            V3 n = vcross(vsub(b, a), vsub(cc, a));          // area weighted
            for (int k = 0; k < 3; k++) VN[tr[k]] = vadd(VN[tr[k]], n);
        }
        for (uint32_t t = 0; t < nt * 3; t++) {
            uint32_t v = T[t]; V3 n = vnorm(VN[v]);
            *w++ = P[v*3]; *w++ = P[v*3+1]; *w++ = P[v*3+2]; *w++ = n.x; *w++ = n.y; *w++ = n.z;
            *w++ = mat[0]; *w++ = mat[1]; *w++ = mat[2];      // diffuse
            *w++ = mat[4]; *w++ = mat[5]; *w++ = mat[6];      // ambient
            *w++ = mat[7]; *w++ = mat[8]; *w++ = mat[9];      // specular
            *w++ = mat[10];                                   // shininess
        }
        static const float side[6] = {-1, 1, 1, -1, 1, -1};
        static const int end[6] = {0, 0, 1, 0, 1, 1};
        // mat[15] > 0 marks section hatching, mat[15] = its spacing in mm (drawn only when there is room)
        float **dst = &lw;
        if (mat[15] > 0) {
            dst = &hw_;
            hatch_step = hatch_step > 0 ? fminf(hatch_step, mat[15] * 0.001f) : mat[15] * 0.001f;
        }
        for (uint32_t s = 0; s + 1 < nl; s += 2) {
            float *A = L + s*3, *B = L + s*3 + 3;
            for (int k = 0; k < 6; k++) {
                float *me = end[k] ? B : A, *ot = end[k] ? A : B, *o = *dst;
                *o++ = me[0]; *o++ = me[1]; *o++ = me[2]; *o++ = ot[0]; *o++ = ot[1]; *o++ = ot[2];
                *o++ = end[k] ? -side[k] : side[k];
                *o++ = mat[11]; *o++ = mat[12]; *o++ = mat[13]; *o++ = mat[14];
                *dst = o;
            }
        }
        free(P); free(T); free(L); free(VN);
    }
    free(buf);
    n_tv = (int)((w - tout) / 16); n_lv = (int)((lw - lout) / 11); n_hv = (int)((hw_ - hout) / 11);
    memcpy(lw, hout, (size_t)n_hv * 44); free(hout);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_t); glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)n_tv * 64, tout, GL_STATIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_l); glBufferData(GL_ARRAY_BUFFER, (GLsizeiptr)(n_lv + n_hv) * 44, lout, GL_STATIC_DRAW);
    free(tout); free(lout);
    have_model = n_tv + n_lv > 0;
    if (have_model) {
        m_center = vmul(vadd(lo, hi), 0.5f); m_lo = lo; m_hi = hi;
        float sz = fmaxf(hi.x - lo.x, fmaxf(hi.y - lo.y, hi.z - lo.z));
        m_size = sz > 1e-5f ? sz : 0.01f;
    }
    printf("loaded %u objects, %d triangles, %d edge segments, size %.1f mm\n", nobj, n_tv / 3, n_lv / 6, m_size * 1000);
    return 1;
}

/* ---------- shaders: FreeCAD-like headlight shading + screen-space edge lines ---------- */
static const char *VS_FACE =
    "#version 330 core\n"
    "layout(location=0) in vec3 p; layout(location=1) in vec3 n; layout(location=2) in vec3 dif;\n"
    "layout(location=3) in vec3 amb; layout(location=4) in vec3 spe; layout(location=5) in float shin;\n"
    "uniform mat4 mvp, model; out vec3 vn, vw, vdif, vamb, vspe; out float vshin;\n"
    "void main(){ gl_Position = mvp*vec4(p,1); vn = mat3(model)*n; vw = (model*vec4(p,1)).xyz;\n"
    "  vdif=dif; vamb=amb; vspe=spe; vshin=shin; }\n";
static const char *FS_FACE =
    "#version 330 core\n"
    "in vec3 vn, vw, vdif, vamb, vspe; in float vshin; uniform vec3 eye; out vec4 o;\n"
    "void main(){ vec3 N = normalize(vn); vec3 V = normalize(eye-vw); if(dot(N,V)<0.0) N=-N;\n"
    // Coin3D/FreeCAD: one headlight at the camera, two-sided lighting, global ambient 0.2
    "  float d = max(dot(N,V),0.0); float s = pow(d, max(vshin*128.0,1.0));\n"
    "  vec3 c = vamb*0.2 + vdif*d + vspe*s;\n"
    "  o = vec4(clamp(c,0.0,1.0),1); }\n";
static const char *VS_LINE =
    "#version 330 core\n"
    "layout(location=0) in vec3 a; layout(location=1) in vec3 b; layout(location=2) in float side;\n"
    "layout(location=3) in vec3 col; layout(location=4) in float width;\n"
    // width is in headset-display pixels (x0.6, at least 1); k = texture pixels per display pixel,
    // so a line keeps its look at any scale. Each segment runs on past its ends by half its width
    // so the short pieces of a curved outline overlap instead of leaving notches at every bend.
    "uniform mat4 mvp; uniform vec2 px; uniform float k; out vec3 vc;\n"
    "void main(){ vec4 A = mvp*vec4(a,1), B = mvp*vec4(b,1);\n"
    "  vec2 sa = A.xy/A.w, sb = B.xy/B.w; vec2 d = (sb-sa)*px; float l = length(d);\n"
    "  vec2 dir = l > 1e-6 ? d/l : vec2(1,0); vec2 nrm = vec2(-dir.y, dir.x);\n"
    "  float hw = l > 1e-3 ? max(width*0.6, 1.0)*k*0.5 : 0.0;\n"      // a zero-length piece draws nothing
    "  A.xy += (nrm*side - dir)*hw/px*A.w; A.z -= 0.0004*A.w;\n"    // nudged in front of faces
    "  gl_Position = A; vc = col; }\n";
static const char *FS_LINE =
    "#version 330 core\n"
    "in vec3 vc; out vec4 o; void main(){ o = vec4(vc,1); }\n";

static GLuint mk_shader(GLenum t, const char *s) {
    GLuint h = glCreateShader(t); glShaderSource(h, 1, &s, NULL); glCompileShader(h);
    GLint ok; glGetShaderiv(h, GL_COMPILE_STATUS, &ok);
    if (!ok) { char log[2048]; glGetShaderInfoLog(h, sizeof log, NULL, log); fprintf(stderr, "shader: %s\n", log); exit(1); }
    return h;
}
static GLuint mk_prog(const char *vs, const char *fs) {
    GLuint p = glCreateProgram();
    glAttachShader(p, mk_shader(GL_VERTEX_SHADER, vs)); glAttachShader(p, mk_shader(GL_FRAGMENT_SHADER, fs));
    glLinkProgram(p); return p;
}
static void attribs(const int *sizes, int count, int stride) {
    int off = 0;
    for (int a = 0; a < count; a++) {
        glEnableVertexAttribArray(a);
        glVertexAttribPointer(a, sizes[a], GL_FLOAT, GL_FALSE, stride, (void *)(intptr_t)off); off += sizes[a] * 4;
    }
}

// Is FreeCAD running? (any process named FreeCAD/freecad; flatpak processes are visible from the host too)
static int freecad_running(void) {
    DIR *d = opendir("/proc"); struct dirent *e; int found = 0;
    if (!d) return 1;
    while (!found && (e = readdir(d))) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        char p[300], comm[32] = ""; snprintf(p, sizeof p, "/proc/%s/comm", e->d_name);
        FILE *f = fopen(p, "r"); if (!f) continue;
        if (fgets(comm, sizeof comm, f)) { comm[strcspn(comm, "\n")] = 0; found = !strcasecmp(comm, "freecad"); }
        fclose(f);
    }
    closedir(d);
    return found;
}

static double now_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec * 1e-9; }

int main(int argc, char **argv) {
    signal(SIGINT, on_sig); signal(SIGTERM, on_sig);
    setvbuf(stdout, NULL, _IOLBF, 0);
    const char *home = getenv("HOME");
    char path[1024], cmdpath[1024], viewpath[1024];
    // --dir DIR: where model.bin/cmd/view live (default ~/.vr-model-viewer, FreeCAD's);
    // --parent-pid PID: close when that process ends (default: when FreeCAD ends)
    char dir[900]; snprintf(dir, sizeof dir, "%s/.vr-model-viewer", home);
    int parent = 0;
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--dir")) snprintf(dir, sizeof dir, "%s", argv[i + 1]);
        else if (!strcmp(argv[i], "--parent-pid")) parent = atoi(argv[i + 1]);
    }
    snprintf(path, sizeof path, "%s/model.bin", dir);
    snprintf(cmdpath, sizeof cmdpath, "%s/cmd", dir);
    snprintf(viewpath, sizeof viewpath, "%s/view", dir);

    // EGL / GL context (surfaceless)
    EGLDisplay dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (!eglInitialize(dpy, NULL, NULL)) { fprintf(stderr, "eglInitialize failed\n"); return 1; }
    eglBindAPI(EGL_OPENGL_API);
    EGLint cattr[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_NONE};
    EGLConfig cfg; EGLint ncfg;
    if (!eglChooseConfig(dpy, cattr, &cfg, 1, &ncfg) || !ncfg) { fprintf(stderr, "no EGL config\n"); return 1; }
    EGLint ctxattr[] = {EGL_CONTEXT_MAJOR_VERSION, 4, EGL_CONTEXT_MINOR_VERSION, 3,
                        EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT, EGL_NONE};
    EGLContext ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctxattr);
    if (!ctx) { fprintf(stderr, "eglCreateContext failed 0x%x\n", eglGetError()); return 1; }
    eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx);
    printf("GL: %s\n", glGetString(GL_RENDERER));

    // OpenVR as an overlay app: the desktop / current scene app keeps running
    EVRInitError err = EVRInitError_VRInitError_None;
    VR_InitInternal(&err, EVRApplicationType_VRApplication_Overlay);
    if (err) { fprintf(stderr, "VR_Init failed: %d\n", err); return 1; }
    struct VR_IVRSystem_FnTable *sys = (void *)VR_GetGenericInterface("FnTable:IVRSystem_022", &err);
    struct VR_IVROverlay_FnTable *ov = (void *)VR_GetGenericInterface("FnTable:IVROverlay_027", &err);
    if (!sys || !ov) { fprintf(stderr, "OpenVR interfaces missing: %d\n", err); return 1; }
    VROverlayHandle_t oh;
    char key[64]; snprintf(key, sizeof key, "fcvr.model.%d", (int)getpid());   // several viewers can run at once
    EVROverlayError oe = ov->CreateOverlay(key, "CAD model", &oh);
    if (oe) { fprintf(stderr, "CreateOverlay: %s\n", ov->GetOverlayErrorNameFromEnum(oe)); return 1; }
    ov->SetOverlayFlag(oh, VROverlayFlags_SideBySide_Parallel, 1);

    // controller input through SteamVR Input (works for overlay apps)
    struct VR_IVRInput_FnTable *in = (void *)VR_GetGenericInterface("FnTable:IVRInput_010", &err);
    char manifest[1100]; snprintf(manifest, sizeof manifest, "%s/fcvr/actions.json", home);
    VRActionSetHandle_t aset = 0; VRActionHandle_t a_grip[2] = {0}, a_stick[2] = {0}, a_pose[2] = {0};
    if (in && !in->SetActionManifestPath(manifest)) {
        in->GetActionSetHandle("/actions/main", &aset);
        in->GetActionHandle("/actions/main/in/grip_left", &a_grip[0]); in->GetActionHandle("/actions/main/in/grip_right", &a_grip[1]);
        in->GetActionHandle("/actions/main/in/stick_left", &a_stick[0]); in->GetActionHandle("/actions/main/in/stick_right", &a_stick[1]);
        in->GetActionHandle("/actions/main/in/pose_left", &a_pose[0]); in->GetActionHandle("/actions/main/in/pose_right", &a_pose[1]);
    } else { fprintf(stderr, "SteamVR Input unavailable; controller scaling off\n"); in = NULL; }
    int held[2] = {0, 0}; V3 g_off[2] = {{0}}; Q g_roff[2] = {{0, 0, 0, 1}, {0, 0, 0, 1}};
    float two_d0 = 0, two_s0 = 1; V3 two_m0 = {0}, two_p0 = {0};
    ov->SetOverlaySortOrder(oh, 10);

    // render targets: MSAA side-by-side buffer resolved into the overlay texture
    int TW = EYE_PX * 2, TH = EYE_PX;
    GLuint ms_fbo, ms_col, ms_dep, out_fbo[2], out_tex[2], res_fbo, res_tex;
    int cur = 0;   // two overlay textures: draw one while SteamVR still shows the other
    glGenRenderbuffers(1, &ms_col); glBindRenderbuffer(GL_RENDERBUFFER, ms_col);
    glRenderbufferStorageMultisample(GL_RENDERBUFFER, MSAA, GL_RGBA8, TW, TH);
    glGenRenderbuffers(1, &ms_dep); glBindRenderbuffer(GL_RENDERBUFFER, ms_dep);
    glRenderbufferStorageMultisample(GL_RENDERBUFFER, MSAA, GL_DEPTH_COMPONENT24, TW, TH);
    glGenFramebuffers(1, &ms_fbo); glBindFramebuffer(GL_FRAMEBUFFER, ms_fbo);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, ms_col);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, ms_dep);
    glGenTextures(2, out_tex); glGenFramebuffers(2, out_fbo);
    for (int i = 0; i < 2; i++) {
        glBindTexture(GL_TEXTURE_2D, out_tex[i]);
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, TW, TH);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR); glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glBindFramebuffer(GL_FRAMEBUFFER, out_fbo[i]);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, out_tex[i], 0);
    }
    // MSAA resolves into this at the frame's own size, then is scaled smoothly into out_tex: SteamVR
    // samples overlays without mipmaps, so a texture much denser than the display would shimmer.
    glGenTextures(1, &res_tex); glBindTexture(GL_TEXTURE_2D, res_tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, TW, TH);
    glGenFramebuffers(1, &res_fbo); glBindFramebuffer(GL_FRAMEBUFFER, res_fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, res_tex, 0);

    GLuint pf = mk_prog(VS_FACE, FS_FACE), pl = mk_prog(VS_LINE, FS_LINE);
    GLint uf_mvp = glGetUniformLocation(pf, "mvp"), uf_model = glGetUniformLocation(pf, "model"), uf_eye = glGetUniformLocation(pf, "eye");
    GLint ul_mvp = glGetUniformLocation(pl, "mvp"), ul_px = glGetUniformLocation(pl, "px"), ul_k = glGetUniformLocation(pl, "k");
    // headset pixels per radian, to keep line widths constant on the display
    uint32_t rw, rh; sys->GetRecommendedRenderTargetSize(&rw, &rh);
    float pl_l, pl_r, pl_t, pl_b; sys->GetProjectionRaw(EVREye_Eye_Left, &pl_l, &pl_r, &pl_t, &pl_b);
    float display_ppr = rw / (atanf(pl_r) - atanf(pl_l));
    glGenVertexArrays(1, &vao_t); glGenBuffers(1, &vbo_t); glBindVertexArray(vao_t); glBindBuffer(GL_ARRAY_BUFFER, vbo_t);
    { int s[] = {3, 3, 3, 3, 3, 1}; attribs(s, 6, 64); }
    glGenVertexArrays(1, &vao_l); glGenBuffers(1, &vbo_l); glBindVertexArray(vao_l); glBindBuffer(GL_ARRAY_BUFFER, vbo_l);
    { int s[] = {3, 3, 1, 3, 1}; attribs(s, 5, 44); }

    // model placement (standing universe, metres, Y up)
    V3 mpos = v3(0, 1.2f, -0.6f); Q mrot = {0, 0, 0, 1}; float mscale = 1, user_yaw = 0;
    int placed = 0, follow = 1, shown = 0;
    long cmd_off = -1; time_t last_mtime = 0; long last_size = -1; double last_poll = 0;
    Q cam = {0, 0, 0, 1}; char last_view[128] = "";
    const Q zup_to_yup_inv = qaxis(v3(1, 0, 0), (float)M_PI / 2);   // undo the loader's Z-up -> Y-up turn

    printf("overlay running; watching %s\n", path);
    while (!g_quit) {
        double t0 = now_s();
        // close together with the app that opened it (also after a crash): check every 2 s, quit after two misses
        static double last_fc_check, started; static int fc_missing;
        if (started == 0) started = t0;
        if (t0 - last_fc_check > 2.0) {
            last_fc_check = t0;
            int alive = parent ? kill(parent, 0) == 0 : freecad_running();
            fc_missing = alive ? 0 : fc_missing + 1;
            if (fc_missing >= 2 && t0 - started > 5) { printf("%s is closed; exiting\n", parent ? "parent" : "FreeCAD"); break; }
        }
        struct VREvent_t ev;
        while (sys->PollNextEvent(&ev, sizeof ev)) if (ev.eventType == EVREventType_VREvent_Quit) {
            sys->AcknowledgeQuit_Exiting(); g_quit = 1;
        }

        // hotkey commands: FreeCAD appends "<seq> <command> [args]" lines to cmd; read the new ones
        {
            FILE *cf = fopen(cmdpath, "r");
            if (cf) {
                fseek(cf, 0, SEEK_END); long end = ftell(cf);
                if (cmd_off < 0 || end < cmd_off) cmd_off = cmd_off < 0 ? end : 0;   // skip old commands; follow truncation
                fseek(cf, cmd_off, SEEK_SET);
                char line[160];
                while (ftell(cf) < end && fgets(line, sizeof line, cf)) {
                    if (!strchr(line, '\n')) break;                              // half-written line: next frame
                    cmd_off = ftell(cf);
                    long seq; char cmd[32]; float x = 0, y = 0, z = 0;
                    if (sscanf(line, "%ld %31s %f %f %f", &seq, cmd, &x, &y, &z) < 2) continue;
                    Q facing = qaxis(v3(0, 1, 0), user_yaw);                     // your view direction at placement
                    if (!strcmp(cmd, "real")) mscale = 1;
                    else if (!strcmp(cmd, "fit")) mscale = 0.35f / m_size;
                    else if (!strcmp(cmd, "big")) mscale = 1.2f / m_size;
                    else if (!strcmp(cmd, "bigger")) mscale *= 1.5f;
                    else if (!strcmp(cmd, "smaller")) mscale /= 1.5f;
                    else if (!strcmp(cmd, "recenter")) placed = 0;
                    else if (!strcmp(cmd, "follow")) follow = !follow;
                    else if (!strcmp(cmd, "scale") && x > 0) mscale = x;
                    else if (!strcmp(cmd, "zoom") && x > 0) mscale *= x;              // relative, e.g. a mouse wheel
                    else if (!strcmp(cmd, "move")) mpos = vadd(mpos, qrot(facing, v3(x, y, z)));  // metres: right, up, back
                    else if (!strcmp(cmd, "rotate")) {                            // degrees about your right / up / view axes
                        V3 ax = qrot(facing, v3(x != 0, y != 0, z != 0));
                        float deg = x != 0 ? x : y != 0 ? y : z;
                        mrot = qmul(qaxis(vnorm(ax), deg * (float)M_PI / 180), mrot); follow = 0;
                    } else if (!strcmp(cmd, "upright")) { mrot = facing; follow = 0; }
                    printf("command: %s (scale %.3f, follow %d)\n", cmd, mscale, follow);
                }
                fclose(cf);
            }
        }

        if (t0 - last_poll > 0.05) {
            last_poll = t0; struct stat st;
            if (!stat(path, &st) && (st.st_mtime != last_mtime || st.st_size != last_size)) {
                if (load_model(path)) { last_mtime = st.st_mtime; last_size = st.st_size; }
            }
            FILE *vf = fopen(viewpath, "r"); char line[128];
            if (vf) {
                if (fgets(line, sizeof line, vf) && strcmp(line, last_view)) {
                    Q q; if (sscanf(line, "%f %f %f %f", &q.x, &q.y, &q.z, &q.w) == 4) { cam = q; strcpy(last_view, line); }
                }
                fclose(vf);
            }
        }

        // head + eyes, predicted to when the frame is shown
        float since_vsync; uint64_t fc; sys->GetTimeSinceLastVsync(&since_vsync, &fc);
        float hz = sys->GetFloatTrackedDeviceProperty(0, ETrackedDeviceProperty_Prop_DisplayFrequency_Float, NULL);
        if (hz < 30) hz = 90;
        // the loop runs just after the compositor's frame sync; this frame is shown at the next one
        float to_photons = sys->GetFloatTrackedDeviceProperty(0, ETrackedDeviceProperty_Prop_SecondsFromVsyncToPhotons_Float, NULL);
        float predict = 2.0f / hz - since_vsync + (to_photons > 0 && to_photons < 0.05f ? to_photons : 0.01f);
        TrackedDevicePose_t poses[1];
        sys->GetDeviceToAbsoluteTrackingPose(ETrackingUniverseOrigin_TrackingUniverseStanding, predict, poses, 1);
        if (!poses[0].bPoseIsValid) { usleep(20000); continue; }
        HmdMatrix34_t H = poses[0].mDeviceToAbsoluteTracking;
        V3 head = m34_pos(H);
        V3 eyes[2];
        for (int e = 0; e < 2; e++) eyes[e] = m34_apply(H, m34_pos(sys->GetEyeToHeadTransform(e)));

        if (have_model && !placed) {
            V3 fwd = v3(-H.m[0][2], 0, -H.m[2][2]); fwd = vnorm(fwd);
            user_yaw = atan2f(-fwd.x, -fwd.z);
            mpos = vadd(head, vadd(vmul(fwd, 0.6f), v3(0, -0.15f, 0)));
            mrot = qaxis(v3(0, 1, 0), user_yaw);
            placed = 1;
        }
        // controllers: grip grabs (moves; also turns it when not following the FreeCAD view),
        // both grips stretch to scale, grip + thumbstick up/down scales
        if (in && have_model) {
            // overlay-global priority: without it the app in front (the desktop) keeps the controllers
            struct VRActiveActionSet_t as = {aset, 0, 0, 0x01000000};
            EVRInputError ue = in->UpdateActionState(&as, sizeof as, 1);
            static double last_dbg; int dbg = t0 - last_dbg > 1.0; if (dbg) last_dbg = t0;
            int grab[2]; V3 hp[2]; Q hq[2];
            for (int h = 0; h < 2; h++) {
                struct InputDigitalActionData_t d; struct InputAnalogActionData_t a; struct InputPoseActionData_t pz;
                memset(&d, 0, sizeof d); memset(&pz, 0, sizeof pz);
                EVRInputError ge = in->GetDigitalActionData(a_grip[h], &d, sizeof d, 0);
                grab[h] = !ge && d.bActive && d.bState;
                if (getenv("FCVR_DEBUG_INPUT") && d.bChanged) printf("grip %s: active %d state %d\n", h ? "right" : "left", d.bActive, d.bState);
                int pv = !in->GetPoseActionDataForNextFrame(a_pose[h], ETrackingUniverseOrigin_TrackingUniverseStanding, &pz, sizeof pz, 0)
                         && pz.bActive && pz.pose.bPoseIsValid;
                if (dbg && getenv("FCVR_DEBUG_INPUT")) printf("input[%d]: update %d grip err %d active %d state %d | pose active %d valid %d\n",
                                h, ue, ge, d.bActive, d.bState, pz.bActive, pz.pose.bPoseIsValid);
                if (!pv) { grab[h] = 0; continue; }
                HmdMatrix34_t M = pz.pose.mDeviceToAbsoluteTracking;
                hp[h] = m34_pos(M);
                float tr = M.m[0][0] + M.m[1][1] + M.m[2][2], qw = sqrtf(fmaxf(0, 1 + tr)) / 2;  // matrix -> quaternion
                Q q = {copysignf(sqrtf(fmaxf(0, 1 + M.m[0][0] - M.m[1][1] - M.m[2][2])) / 2, M.m[2][1] - M.m[1][2]),
                       copysignf(sqrtf(fmaxf(0, 1 - M.m[0][0] + M.m[1][1] - M.m[2][2])) / 2, M.m[0][2] - M.m[2][0]),
                       copysignf(sqrtf(fmaxf(0, 1 - M.m[0][0] - M.m[1][1] + M.m[2][2])) / 2, M.m[1][0] - M.m[0][1]), qw};
                hq[h] = q;
                if (grab[h] && !in->GetAnalogActionData(a_stick[h], &a, sizeof a, 0) && a.bActive && fabsf(a.y) > 0.2f)
                    mscale *= expf(a.y * 1.5f / hz);
            }
            if (grab[0] && grab[1]) {
                V3 mid = vmul(vadd(hp[0], hp[1]), 0.5f); float d = vlen(vsub(hp[0], hp[1]));
                if (!(held[0] && held[1])) { two_d0 = fmaxf(d, 0.01f); two_s0 = mscale; two_m0 = mid; two_p0 = mpos; }
                float ratio = d / two_d0; mscale = two_s0 * ratio;
                mpos = vadd(mid, vmul(vsub(two_p0, two_m0), ratio));
                held[0] = held[1] = 1;
            } else {
                for (int h = 0; h < 2; h++) if (grab[h]) {
                    if (!held[h] || held[!h]) { Q iq = qinv(hq[h]); g_off[h] = qrot(iq, vsub(mpos, hp[h])); g_roff[h] = qmul(iq, mrot); }
                    mpos = vadd(hp[h], qrot(hq[h], g_off[h]));
                    if (!follow) mrot = qmul(hq[h], g_roff[h]);
                }
                held[0] = grab[0]; held[1] = grab[1];
            }
        }

        if (follow) // turn the model like the FreeCAD view: the user's facing direction is FreeCAD's camera
            mrot = qmul(qmul(qaxis(v3(0, 1, 0), user_yaw), qinv(cam)), zup_to_yup_inv);

        if (!have_model) { if (shown) { ov->HideOverlay(oh); shown = 0; } usleep(50000); continue; }

        // Sheet: a plane at the model's depth facing you, covering (model outline) ∩ (field of view).
        // It is kept still while it still covers what is needed, so it doesn't swim as your head moves.
        V3 mid = vmul(vadd(eyes[0], eyes[1]), 0.5f);
        V3 F = vnorm(v3(-H.m[0][2], -H.m[1][2], -H.m[2][2])), Rh = v3(H.m[0][0], H.m[1][0], H.m[2][0]);
        V3 Rt = vnorm(vsub(Rh, vmul(F, vdot(Rh, F)))), Ut = vcross(vmul(F, -1), Rt);
        float D = fmaxf(vdot(vsub(mpos, mid), F), 0.15f);
        V3 P0 = vadd(mid, vmul(F, D));
        float fx = 0, fy = 0;                                  // field of view half extents on the plane
        for (int e = 0; e < 2; e++) {
            float l, r, t, b; sys->GetProjectionRaw(e, &l, &r, &t, &b);
            fx = fmaxf(fx, fmaxf(fabsf(l), fabsf(r))); fy = fmaxf(fy, fmaxf(fabsf(t), fabsf(b)));
        }
        float x0 = -fx * D * 1.1f - 0.04f, x1 = -x0, y0 = -fy * D * 1.1f - 0.04f, y1 = -y0;
        float mx0 = 1e9f, mx1 = -1e9f, my0 = 1e9f, my1 = -1e9f; int unbounded = 0;
        for (int c = 0; c < 8; c++) {                          // model box corners projected onto the plane
            V3 lc = v3(c & 1 ? m_hi.x : m_lo.x, c & 2 ? m_hi.y : m_lo.y, c & 4 ? m_hi.z : m_lo.z);
            V3 wc = vadd(mpos, qrot(mrot, vmul(vsub(lc, m_center), mscale)));
            V3 v = vsub(wc, mid); float z = vdot(v, F);
            if (z < 0.05f) { unbounded = 1; break; }
            v = vmul(v, D / z);
            float px = vdot(v, Rt), py = vdot(v, Ut);
            mx0 = fminf(mx0, px); mx1 = fmaxf(mx1, px); my0 = fminf(my0, py); my1 = fmaxf(my1, py);
        }
        if (!unbounded) {
            float pad = 0.05f * fmaxf(mx1 - mx0, my1 - my0) + 0.01f;
            x0 = fmaxf(x0, mx0 - pad); x1 = fminf(x1, mx1 + pad); y0 = fmaxf(y0, my0 - pad); y1 = fminf(y1, my1 + pad);
        }
        if (x1 <= x0 || y1 <= y0) {                           // model is out of view
            if (shown) { ov->HideOverlay(oh); shown = 0; }
            usleep(11000); continue;
        }
        float need = fmaxf(x1 - x0, y1 - y0);
        V3 need_c = vadd(P0, vadd(vmul(Rt, (x0 + x1) / 2), vmul(Ut, (y0 + y1) / 2)));
        // keep the current sheet if it still contains the needed rectangle (seen from the eyes) and isn't too big
        static V3 S_c, S_R, S_U, S_N; static float S_w = 0;
        int keep = S_w > 0 && vdot(S_N, vmul(F, -1)) > cosf(30 * (float)M_PI / 180);
        if (keep) {
            float sd = vdot(vsub(S_c, mid), vmul(S_N, -1)), nd = 0;
            for (int c = 0; c < 4 && keep; c++) {
                V3 corner = vadd(P0, vadd(vmul(Rt, c & 1 ? x1 : x0), vmul(Ut, c & 2 ? y1 : y0)));
                V3 v = vsub(corner, mid); float z = vdot(v, vmul(S_N, -1));
                if (z < 0.01f) { keep = 0; break; }
                V3 on = vsub(vadd(mid, vmul(v, sd / z)), S_c);
                float ux = vdot(on, S_R), uy = vdot(on, S_U);
                if (fabsf(ux) > S_w / 2 || fabsf(uy) > S_w / 2) keep = 0;
                nd = fmaxf(nd, fmaxf(fabsf(ux), fabsf(uy)) * 2);
            }
            if (keep && S_w > 2.2f * nd) keep = 0;             // much bigger than needed: wastes resolution
        }
        if (!keep) { S_c = need_c; S_R = Rt; S_U = Ut; S_N = vmul(F, -1); S_w = need * 1.25f; }
        V3 Rr = S_R, Uu = S_U, Nn = S_N; float sheet = S_w;
        HmdMatrix34_t X = {{{Rr.x, Uu.x, Nn.x, S_c.x}, {Rr.y, Uu.y, Nn.y, S_c.y}, {Rr.z, Uu.z, Nn.z, S_c.z}}};

        float sheet_d = fmaxf(vdot(vsub(S_c, mid), vmul(S_N, -1)), 0.05f);
        // n: this frame's per-eye resolution, ~2 render pixels per headset pixel; k: their ratio
        float sheet_px = 2 * atanf(sheet / 2 / sheet_d) * display_ppr;
        int n = (int)fminf(fmaxf(ceilf(2 * sheet_px), 256), EYE_PX);
        float k = n / sheet_px;

        // render both eyes
        M4 model = mmul(m_from(mrot, mpos, mscale), m_from((Q){0, 0, 0, 1}, vmul(m_center, -1), 1));
        glBindFramebuffer(GL_FRAMEBUFFER, ms_fbo);
        glViewport(0, 0, 2 * n, n); glClearColor(0, 0, 0, 0); glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        glEnable(GL_DEPTH_TEST);
        for (int e = 0; e < 2; e++) {
            glViewport(e * n, 0, n, n);
            M4 vp = window_mvp(eyes[e], S_c, Rr, Uu, sheet, sheet, 0.02f, 50);
            M4 mvp = mmul(vp, model);
            glUseProgram(pf);
            glUniformMatrix4fv(uf_mvp, 1, GL_FALSE, mvp.m); glUniformMatrix4fv(uf_model, 1, GL_FALSE, model.m);
            glUniform3f(uf_eye, eyes[e].x, eyes[e].y, eyes[e].z);
            glEnable(GL_POLYGON_OFFSET_FILL); glPolygonOffset(1, 2);
            glBindVertexArray(vao_t); glDrawArrays(GL_TRIANGLES, 0, n_tv);
            glDisable(GL_POLYGON_OFFSET_FILL);
            glUseProgram(pl);
            glUniformMatrix4fv(ul_mvp, 1, GL_FALSE, mvp.m); glUniform2f(ul_px, n / 2.0f, n / 2.0f);
            glUniform1f(ul_k, k);
            glBindVertexArray(vao_l); glDrawArrays(GL_TRIANGLES, 0, n_lv);
            if (n_hv && hatch_step * mscale / sheet_d * display_ppr >= 5)   // >= 5 headset px apart
                glDrawArrays(GL_TRIANGLES, n_lv, n_hv);
        }
        glBindFramebuffer(GL_READ_FRAMEBUFFER, ms_fbo); glBindFramebuffer(GL_DRAW_FRAMEBUFFER, res_fbo);
        glBlitFramebuffer(0, 0, 2 * n, n, 0, 0, 2 * n, n, GL_COLOR_BUFFER_BIT, GL_NEAREST);    // resolve
        glBindFramebuffer(GL_READ_FRAMEBUFFER, res_fbo); cur ^= 1; glBindFramebuffer(GL_DRAW_FRAMEBUFFER, out_fbo[cur]);
        for (int e = 0; e < 2; e++)                                                          // and scale
            glBlitFramebuffer(e * n, 0, e * n + n, n, e * EYE_PX, 0, e * EYE_PX + EYE_PX, EYE_PX, GL_COLOR_BUFFER_BIT, GL_LINEAR);
        {   // FCVR_DUMP=file.ppm: save the left eye once (on grey), to check the rendering without a headset
            static int dumped, frames; const char *dump = getenv("FCVR_DUMP");
            if (dump && !dumped && ++frames == (getenv("FCVR_DUMP_FRAME") ? atoi(getenv("FCVR_DUMP_FRAME")) : 45)) {
                unsigned char *px = malloc((size_t)EYE_PX * EYE_PX * 4); FILE *f = fopen(dump, "wb");
                glBindFramebuffer(GL_READ_FRAMEBUFFER, out_fbo[cur]);
                glReadPixels(0, 0, EYE_PX, EYE_PX, GL_RGBA, GL_UNSIGNED_BYTE, px);
                if (f) {
                    fprintf(f, "P6 %d %d 255\n", EYE_PX, EYE_PX);
                    for (int y = EYE_PX - 1; y >= 0; y--) for (int x = 0; x < EYE_PX; x++) {
                        unsigned char *p = px + ((size_t)y * EYE_PX + x) * 4;
                        for (int c = 0; c < 3; c++) fputc(p[c] + (255 - p[3]) * 160 / 255, f);
                    }
                    fclose(f);
                }
                free(px); dumped = 1;
                printf("dump: n %d, sheet %.3f m at %.3f m, k %.2f, scale %.3f, model %.1f mm, need %.3f\n",
                       n, sheet, sheet_d, k, mscale, m_size * 1000, need);
            }
        }
        glFinish();
        struct Texture_t tex = {(void *)(uintptr_t)out_tex[cur], ETextureType_TextureType_OpenGL, EColorSpace_ColorSpace_Gamma};
        oe = ov->SetOverlayTexture(oh, &tex);
        // move the sheet only now, next to the image drawn for it, so the two land in the same frame
        ov->SetOverlayTransformAbsolute(oh, ETrackingUniverseOrigin_TrackingUniverseStanding, &X);
        ov->SetOverlayWidthInMeters(oh, sheet);
        if (oe) { static int once; if (!once++) fprintf(stderr, "SetOverlayTexture: %s\n", ov->GetOverlayErrorNameFromEnum(oe)); }
        if (!shown) { ov->ShowOverlay(oh); shown = 1; }
        if (getenv("FCVR_DEBUG_TIME")) { static int frame_no; if (++frame_no % 90 == 0) { static double last; double t = now_s(); printf("frame %.1f ms, %.1f fps, sheet %.2f m, n %d, k %.2f\n", (t - t0) * 1000, 90 / (t - last), sheet, n, k); last = t; } }

        if (ov->WaitFrameSync(100)) {                  // pace on the compositor; a timer if that fails
            double spent = now_s() - t0, frame = 1.0 / hz;
            if (spent < frame) usleep((useconds_t)((frame - spent) * 1e6));
        }
    }
    printf("exiting\n");
    VR_ShutdownInternal();
    return 0;
}
