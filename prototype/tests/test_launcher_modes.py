"""T1/T2 selection and role cards without Tcl, desktop input or game processes."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from contextlib import ExitStack

from prototype import guided_ui, launcher
from prototype.tests.test_guided_launcher import STEPS, status
from prototype.tests.test_update_startup import Value, headless_app


T1, T2 = launcher.workflow.GUIDED_MODE, launcher.workflow.RAIL_MODE


class TracedValue(Value):
    def __init__(self, value=""):
        super().__init__(value)
        self.callbacks = []

    def trace_add(self, _kind, callback):
        self.callbacks.append(callback)

    def set(self, value):
        super().set(value)
        for callback in self.callbacks:
            callback()


class Notebook:
    """Record the real builder's tab wiring without creating Tk widgets."""
    def __init__(self, *_args, **_kwargs):
        self.pages = {}
        self.selected = ""
        self.pack = Mock()
        self.bind = Mock()

    def add(self, page, **options):
        self.pages.setdefault(str(page), {}).update(options | {"state": "normal"})
        if not self.selected:
            self.selected = str(page)

    def hide(self, page):
        self.pages[str(page)]["state"] = "hidden"

    def select(self, page=None):
        if page is not None:
            self.selected = str(page)
        return self.selected

    def tab(self, page, **options):
        self.pages[str(page)].update(options)


def mode_app(mode=T1):
    app = headless_app()
    app.busy = False
    app.test_mode = TracedValue(mode)
    app._selected_test_mode = mode
    app._mode_selection_guard = False
    app.test_mode.trace_add("write", app._mode_requested)
    app.host, app.code, app.role = Value("127.0.0.1"), Value("fixture private code"), Value("b")
    app.game = Value("fixture-game")
    app.saves = Value("fixture-saves")
    app.guided_pending_sequence = app.guided_pending_revision = app.guided_pending_index = None
    app.last_run = None
    for name in ("save_name", "network", "engine", "progress_text"):
        setattr(app, name, Value())
    app.bar = {}
    app.game_button = Mock()
    app._buttons = Mock()
    app._work = Mock()
    return app


class LauncherModeTests(unittest.TestCase):
    def test_actual_builder_has_two_primary_tabs_one_action_and_hidden_settings(self):
        notebooks = []
        def notebook(*args, **kwargs):
            item = Notebook(*args, **kwargs)
            notebooks.append(item)
            return item
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            stack.enter_context(patch.object(launcher.workflow, "local_root", return_value=Path(directory)))
            stack.enter_context(patch.object(launcher.workflow, "read_json", return_value={}))
            stack.enter_context(patch.object(launcher.test_pairing, "load_profile", return_value=None))
            stack.enter_context(patch.object(launcher.tk, "StringVar", side_effect=lambda value="": TracedValue(value)))
            stack.enter_context(patch.object(launcher.tk, "Tk", side_effect=AssertionError("No desktop windows")))
            stack.enter_context(patch.object(launcher.tk, "Canvas", side_effect=lambda *_a, **_k: Mock()))
            for name in ("Style", "Frame", "Label", "LabelFrame", "Button", "Radiobutton", "Entry",
                         "Scrollbar", "Treeview", "Progressbar", "Combobox"):
                stack.enter_context(patch.object(launcher.ttk, name, side_effect=lambda *_a, **_k: Mock()))
            stack.enter_context(patch.object(launcher.ttk, "Notebook", side_effect=notebook))
            stack.enter_context(patch.object(launcher.App, "_work"))
            stack.enter_context(patch.object(launcher, "game_is_running", return_value=False))
            app = launcher.App(Mock(), skip_update=True)
            main = notebooks[0]
            visible = [page["text"] for page in main.pages.values() if page["state"] != "hidden"]
            self.assertEqual(visible, ["T1 · Straße", "T2 · Schiene"])
            self.assertEqual(main.select(), str(app.main_test_pages[T2]))
            app.advanced_frame.pack.assert_not_called()
            self.assertEqual(sum(button is app.guided_action_button for button in app.wizard_buttons), 1)
            main.select(app.main_test_pages[T1])
            app._tab_requested()
            self.assertEqual(app.test_mode.get(), T1)
            self.assertEqual(main.select(), str(app.main_test_pages[T1]))

    def test_new_launcher_defaults_to_t2_and_retains_private_pairing(self):
        profile = {"host": "127.0.0.1", "code": "fixture private code", "role": "b"}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher.workflow, "local_root", return_value=Path(directory)), \
             patch.object(launcher.workflow, "read_json", return_value={}), \
             patch.object(launcher.test_pairing, "load_profile", return_value=profile), \
             patch.object(launcher.tk, "StringVar", side_effect=lambda value="": TracedValue(value)), \
             patch.object(launcher.tk, "Tk", side_effect=AssertionError("No desktop windows")), \
             patch.object(launcher.App, "_build"), patch.object(launcher.App, "_work"):
            app = launcher.App(Mock(), skip_update=True)
        self.assertEqual(app.test_mode.get(), T2)
        self.assertEqual(app._selected_test_mode, T2)
        self.assertEqual((app.host.get(), app.code.get(), app.role.get()),
                         (profile["host"], profile["code"], profile["role"]))

    def test_idle_switch_uses_new_catalogue_without_changing_private_profile(self):
        app = mode_app()
        app.last_live_status = status()
        with patch.object(launcher, "game_is_running", return_value=False), \
             patch.object(launcher.workflow, "restore_probe") as restore:
            self.assertTrue(app.select_test_mode(T2))
            self.assertEqual(app.test_mode.get(), T2)
            self.assertEqual(app.last_live_status, {})
            self.assertTrue(app.select_test_mode(T1))
        restore.assert_not_called()
        self.assertEqual((app.host.get(), app.code.get(), app.role.get()),
                         ("127.0.0.1", "fixture private code", "b"))

    def test_prepared_mode_switch_commits_only_after_owned_restore(self):
        app = mode_app()
        run = SimpleNamespace(test_mode=T1, role="b", game_dir="owned-previous-game")
        app.prepared = app.last_run = run
        app.save_name.set("old-imported-save.sav")
        with patch.object(launcher, "game_is_running", return_value=False), \
             patch.object(launcher.workflow, "restore_probe", return_value={"restored": True}) as restore:
            self.assertTrue(app.select_test_mode(T2))
            self.assertIs(app.prepared, run)
            self.assertEqual(app.test_mode.get(), T1)
            self.assertEqual(app.save_name.get(), "old-imported-save.sav")
            job, completed = app._work.call_args.args
            result = job()
            restore.assert_called_once_with("owned-previous-game")
            completed(result)
        self.assertIsNone(app.prepared)
        self.assertIsNone(app.controller)
        self.assertIs(app.last_run, run)
        self.assertEqual(app.test_mode.get(), T2)
        self.assertNotEqual(app.save_name.get(), "old-imported-save.sav")

    def test_changed_installation_or_restore_failure_keeps_old_mode_and_identity(self):
        app = mode_app()
        run = SimpleNamespace(test_mode=T1, role="b", game_dir="owned-previous-game")
        app.prepared = app.last_run = run
        with patch.object(launcher, "game_is_running", return_value=False), \
             patch.object(launcher.workflow, "restore_probe", side_effect=ValueError("owned file changed")):
            app.select_test_mode(T2)
            job, _completed = app._work.call_args.args
            with self.assertRaisesRegex(ValueError, "owned file changed"):
                job()
        self.assertEqual(app.test_mode.get(), T1)
        self.assertIs(app.prepared, run)
        self.assertIs(app.last_run, run)

    def test_busy_live_diagnostic_and_running_game_never_switch(self):
        for condition in ("busy", "controller", "diagnostic", "game"):
            app = mode_app()
            if condition == "busy":
                app.busy = True
            elif condition == "controller":
                app.controller = Mock()
                app.controller.alive.return_value = True
            elif condition == "diagnostic":
                app.diagnostic = object()
            with self.subTest(condition=condition), \
                 patch.object(launcher, "game_is_running", return_value=condition == "game"), \
                 patch.object(launcher.workflow, "restore_probe") as restore:
                self.assertFalse(app.select_test_mode(T2))
                self.assertEqual(app.test_mode.get(), T1)
                app._work.assert_not_called()
                restore.assert_not_called()

    def test_advanced_variable_cannot_bypass_active_session_guard(self):
        app = mode_app()
        app.prepared = SimpleNamespace(test_mode=T1, role="b", game_dir="owned-game")
        app.controller = Mock()
        app.controller.alive.return_value = True
        app.test_mode.set(T2)
        self.assertEqual(app.test_mode.get(), T1)
        self.assertEqual(app._selected_test_mode, T1)
        self.assertEqual(app.prepared.test_mode, T1)
        app._work.assert_not_called()

    def test_direct_prepare_cannot_retarget_an_existing_prepared_run(self):
        app = mode_app()
        app.prepared = SimpleNamespace(test_mode=T1, role="b", game_dir="owned-game")
        # Deliberately bypass the UI trace to exercise the handler's own guard.
        app.test_mode = Value(T2)
        app.prepare()
        app._work.assert_not_called()
        self.assertEqual(app.prepared.test_mode, T1)

    def test_late_wrong_mode_progress_cannot_send_a_different_catalogue_command(self):
        for mode, other in ((T1, T2), (T2, T1)):
            app = mode_app(mode)
            app.prepared = SimpleNamespace(test_mode=mode, role="a")
            app.controller = Mock()
            app.controller.poll.return_value = status() | {"test_mode": other}
            with self.subTest(mode=mode), patch.object(launcher.workflow, "guided_steps") as catalog:
                app.submit_guided()
                app.controller.submit_live.assert_not_called()
                catalog.assert_not_called()

    def test_t1_and_t2_button_submit_their_current_actor_catalogue_once(self):
        for mode in (T1, T2):
            steps = launcher.workflow.guided_steps(mode)
            item = steps[0]
            source = status() | {"test_mode": mode, "role": item["actor"]}
            source["live"]["guided"].update(step_id=item["id"], total_steps=len(steps))
            app = mode_app(mode)
            app.prepared = SimpleNamespace(test_mode=mode, role=item["actor"])
            app.controller = Mock()
            app.controller.poll.side_effect = lambda: deepcopy(source)
            app.controller.submit_live.return_value = 7
            with self.subTest(mode=mode), patch.object(launcher.workflow, "live_input_ready", return_value=True):
                app.submit_guided()
                app.submit_guided()
                app.controller.submit_live.assert_called_once_with(item["command"])
                self.assertEqual(app.guided_pending_sequence, 7)

    def test_t2_poll_status_describes_current_rail_step_instead_of_old_pause_test(self):
        steps = launcher.workflow.guided_steps(T2)
        source = status() | {"test_mode": T2}
        source["live"]["guided"].update(step_id=steps[0]["id"], total_steps=len(steps))
        description = launcher.workflow.describe_status(source)
        self.assertEqual(description, launcher.workflow.guided_input_status(source))
        self.assertIn(steps[0]["instruction"], description)
        self.assertNotIn("45 Sekunden", description)
        self.assertNotIn("Messung gemeinsam abschließen", description)

    def test_t2_card_keeps_role_chapter_and_real_command_without_local_next(self):
        steps = deepcopy(STEPS)
        for item in steps:
            item["command"]["op"] = "RAIL_ACTION"
            item["chapter_title"] = "Signale und Fahrweg"
            item["verification"] = "Signal und Gleiszuordnung stimmen auf beiden PCs überein."
        source = status() | {"test_mode": T2}
        host = guided_ui.card(source, steps, role="a", available=True)
        friend = guided_ui.card(source, steps, role="b", available=True)
        self.assertEqual(host.chapter, "Signale und Fahrweg")
        self.assertIn("Geprüft wird: Signal", host.instruction)
        self.assertTrue(host.enabled)
        self.assertFalse(friend.enabled)
        self.assertEqual(host.command, {"op": "RAIL_ACTION", "step": 1})
        self.assertEqual(host.completed, 0)
        source["live"]["confirmed_paused"] = None
        waiting = guided_ui.card(source, steps, role="a", available=True)
        self.assertIsNone(waiting.command)
        self.assertEqual(waiting.actor, "Beide")
        self.assertEqual(waiting.completed, 0)

    def test_installed_t1_and_t2_catalogues_preserve_role_and_startup_gates(self):
        for mode, op in ((T1, "GUIDED_ACTION"), (T2, "RAIL_ACTION")):
            steps = launcher.workflow.guided_steps(mode)
            self.assertGreater(len(steps), 0)
            for index, item in enumerate(steps):
                source = status() | {"test_mode": mode}
                source["live"]["guided"] = {
                    "index": index, "step": item["step"], "step_id": item["id"],
                    "completed_step_ids": [prior["id"] for prior in steps[:index]],
                    "completed_steps": index, "total_steps": len(steps), "phase": "ready", "ready": True,
                }
                for role in ("a", "b"):
                    with self.subTest(mode=mode, step=item["id"], role=role):
                        view = guided_ui.card(source, steps, role=role, available=True)
                        self.assertEqual(view.enabled, role == item["actor"])
                        self.assertEqual(view.command, {"op": op, "step": index + 1})
                        self.assertEqual(view.completed, index)
                        if mode == T2:
                            self.assertEqual(view.chapter, item["chapter_title"])
                if index == 0:
                    for fault in ("short_setup", "one_loaded", "unconfirmed"):
                        pending = deepcopy(source)
                        if fault == "short_setup":
                            pending["round"] = 9
                        elif fault == "one_loaded":
                            pending["live"]["started"] = False
                        else:
                            pending["live"]["confirmed_paused"] = None
                        waiting = guided_ui.card(pending, steps, role=item["actor"], available=True)
                        self.assertFalse(waiting.enabled)
                        self.assertIsNone(waiting.command)
                        self.assertEqual(waiting.completed, 0)


class LauncherRestoreIntegrationTests(unittest.TestCase):
    def installed_app(self):
        from prototype.tests.test_probe_install import InstallTests
        fixture = InstallTests("test_install_and_restore_preserve_alpha_exactly_and_save_metadata")
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.execute()
        app = mode_app()
        run = SimpleNamespace(test_mode=T1, role="b", game_dir=str(fixture.game))
        app.prepared = app.last_run = run
        return fixture, app, run

    def test_tab_uses_actual_owned_journal_then_requires_new_prepare(self):
        fixture, app, run = self.installed_app()
        with patch.object(launcher, "game_is_running", return_value=False):
            app.select_test_mode(T2)
            job, done = app._work.call_args.args
            result = job()
            self.assertTrue(result["restored"])
            self.assertIs(app.prepared, run)
            self.assertEqual(app.test_mode.get(), T1)
            done(result)
        self.assertEqual(fixture.game_bytes(), fixture.original_game)
        self.assertIsNone(app.prepared)
        self.assertEqual(app.test_mode.get(), T2)
        self.assertIs(app.last_run, run)

    def test_actual_restore_detects_game_started_after_tab_click_without_writes(self):
        from coop.install import _files
        from prototype.strict_sync import probe_install
        fixture, app, run = self.installed_app()
        with patch.object(launcher, "game_is_running", return_value=False):
            app.select_test_mode(T2)
        job, _done = app._work.call_args.args
        before = _files(fixture.game)
        with patch.object(probe_install.native, "game_is_running", return_value=True):
            with self.assertRaisesRegex(probe_install.ProbeInstallError, "geschlossen"):
                job()
        self.assertEqual(_files(fixture.game), before)
        self.assertIs(app.prepared, run)
        self.assertEqual(app.test_mode.get(), T1)

    def test_actual_changed_file_refuses_tab_restore_without_partial_changes(self):
        from coop.install import _files
        from prototype.strict_sync import probe_install
        fixture, app, run = self.installed_app()
        (fixture.game / "alut.dll").write_bytes(b"user changed owned path")
        before = _files(fixture.game)
        with patch.object(launcher, "game_is_running", return_value=False):
            app.select_test_mode(T2)
            job, _done = app._work.call_args.args
            with self.assertRaisesRegex(probe_install.ProbeInstallError, "Wiederherstellung blockiert"):
                job()
        self.assertEqual(_files(fixture.game), before)
        self.assertIs(app.prepared, run)
        self.assertEqual(app.test_mode.get(), T1)


if __name__ == "__main__":
    unittest.main()
