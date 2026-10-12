# Starts VRLiveExport with the FreeCAD GUI (see vr_live_export.py).
try:
    import vr_live_export
    vr_live_export.start()
except Exception as e:
    import FreeCAD
    FreeCAD.Console.PrintWarning("VRLiveExport did not start: %s\n" % e)
