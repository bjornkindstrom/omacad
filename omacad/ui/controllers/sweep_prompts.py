"""Sweep, Loft and Pipe prompts for MainWindow (Björn #46)."""

from PySide6.QtWidgets import QMessageBox

from omacad.ui.controllers.prompt_guards import leaves_sketch


class SweepPromptsMixin:
    """One panel for the three path/profile tools: pick profiles in the view, choose the path sketch, live preview."""

    @leaves_sketch
    def prompt_sweep_tool(self, mode: str):
        from omacad.model.features.sweep import LoftFeature, PipeFeature, SweepFeature
        from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog, TITLES
        title = TITLES[mode]
        if not self.doc.sketches:
            QMessageBox.information(self, title, "Draw the profile and the path in sketches first.")
            return
        if self.inspector.current_tool_dlg is not None:
            return
        dlg = SweepLoftDialog(self.doc, mode, self, embedded=True)
        if mode != "loft" and dlg.cmb_path.count() == 0:
            QMessageBox.information(self, title, "No sketch has lines, arcs or a circle to use as the path.")
            return
        shown = {sid: sk.visible for sid, sk in self.doc.sketches.items()}
        for sk in self.doc.sketches.values():          # the profiles must be visible to be clicked
            sk.visible = True
        self.doc.selected_profile, self.doc.selected_extra = None, []
        self.dock(dlg)

        def feature():
            path = dlg.path()
            if mode == "pipe":
                return PipeFeature("preview", title, path, dlg.spn_diam.value(), dlg.spn_thick.value(), dlg.operation())
            if not dlg.profiles:
                return None
            if mode == "sweep":
                sid, idx = dlg.profiles[0]
                return SweepFeature("preview", title, sid, idx, path, dlg.operation(), dlg.spn_twist.value())
            if len(dlg.profiles) < 2:
                return None
            return LoftFeature("preview", title, [LoftFeature.section_ref(self.doc, s, i) for s, i in dlg.profiles],
                               dlg.operation())

        def preview():
            solid = None
            try:
                feat = feature()
                solid = feat.build_solid(self.doc) if feat is not None else None
                dlg.lbl_problem.setText("" if solid is not None or feat is None
                                        else "No solid from these choices (does the path run from the profile?).")
            except Exception as exc:
                dlg.lbl_problem.setText(str(exc))
            self.viewport.set_preview(solid, dlg.operation())

        def on_pick():
            chosen = ([self.doc.selected_profile] if self.doc.selected_profile else []) + list(self.doc.selected_extra)
            dlg.set_profiles(chosen[:1] if mode == "sweep" else chosen)

        def on_finished(result):
            self.viewport.profile_picked.disconnect(on_pick)
            self.viewport.set_preview(None)
            for sid, vis in shown.items():
                if sid in self.doc.sketches:
                    self.doc.sketches[sid].visible = vis
            self.doc.selected_profile, self.doc.selected_extra = None, []
            if result:
                path, op = dlg.path(), dlg.operation()
                try:
                    if mode == "pipe":
                        feat = self.doc.add_pipe(path, dlg.spn_diam.value(), dlg.spn_thick.value(), op)
                    elif mode == "sweep" and dlg.profiles:
                        feat = self.doc.add_sweep(*dlg.profiles[0], path, op, dlg.spn_twist.value())
                    elif mode == "loft" and len(dlg.profiles) >= 2:
                        feat = self.doc.add_loft(dlg.profiles, op)
                    else:
                        self.status_label.setText(f"{title}: pick the profile(s) first.")
                        return
                    feat.exprs = dlg.get_expressions()
                    self.status_label.setText(f"{feat.name} created.")
                except Exception as exc:
                    self.status_label.setText(f"{title}: {exc}")
            self.doc.notify_changed()

        self.viewport.profile_picked.connect(on_pick)
        self._connect_debounced_preview(dlg, preview)
        dlg.finished.connect(on_finished)
        self.status_label.setText(f"{title}: " + ("set the path and the diameter." if mode == "pipe" else
                                                  "click the profile." if mode == "sweep" else
                                                  "click the first profile, Shift+click the next ones in order."))
        self.doc.notify_changed()
        preview()
