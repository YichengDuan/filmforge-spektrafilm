#!/usr/bin/env python3
"""Offscreen Qt startup smoke; no user config or existing app touched."""
import os
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
from qtpy.QtWidgets import QApplication
from spektrafilm_gui import persistence
import spektrafilm_gui.app as app_module
root=Path(__file__).resolve().parents[1]
persistence.default_gui_state_path=lambda: root/'.config'/'gui-test-state.json'
app=QApplication.instance() or QApplication([])
gui=app_module.create_app()
assert gui.main_window is not None and gui.viewer is not None
print('Original Qt/napari GUI objects constructed successfully; offscreen, no desktop rendering claim')
gui.main_window.close()
gui.viewer.close()
app.processEvents()
