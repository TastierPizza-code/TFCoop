"""Role, receipt and retry boundaries of the real launcher, without Tk or TF2."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from prototype import guided_ui, launcher
from prototype.tests.test_update_startup import Value


STEPS = (
    {"id": "host_pause", "step": 1, "title": "Host pausiert", "actor": "a",
     "instruction": "Host pausiert gemeinsam.", "action_label": "Gemeinsam pausieren",
     "command": {"op": "GUIDED_ACTION", "step": 1}},
    {"id": "friend_vehicle", "step": 2, "title": "Freund kauft Fahrzeug", "actor": "b",
     "instruction": "Freund kauft am Testdepot.", "action_label": "Fahrzeug kaufen",
     "command": {"op": "GUIDED_ACTION", "step": 2}},
)


def progress(index=0, **changes):
    result = {"index": index, "step": index + 1 if index < len(STEPS) else None,
              "step_id": STEPS[index]["id"] if index < len(STEPS) else None,
              "completed_step_ids": [item["id"] for item in STEPS[:index]],
              "completed_steps": index, "total_steps": len(STEPS), "settled_revision": index,
              "phase": "ready" if index < len(STEPS) else "completed", "pending": False, "error": ""}
    return result | changes


def status(index=0):
    return {"test_mode": "guided_suite_v1", "role": "a", "alive": True, "peer_started": True,
            "failure": "", "stopping": False, "completed": False, "finish_requested": False,
            "live": {"started": True, "guided": progress(index), "acknowledged_seq": {"a": 0, "b": 0}}}


class GuidedViewTests(unittest.TestCase):
    def test_only_current_actor_gets_catalog_action_and_read_only_state(self):
        source = status()
        original = deepcopy(source)
        host = guided_ui.card(source, STEPS, role="a", available=True)
        friend = guided_ui.card(source, STEPS, role="b", available=True)
        self.assertTrue(host.enabled)
        self.assertEqual(host.command, {"op": "GUIDED_ACTION", "step": 1})
        self.assertFalse(friend.enabled)
        self.assertEqual(friend.action_label, "Warte auf Host")
        self.assertEqual(host.completed, 0)
        self.assertEqual(source, original)
        host.command["step"] = 99
        self.assertEqual(STEPS[0]["command"]["step"], 1)

    def test_only_settled_guided_prefix_is_evidence(self):
        source = status()
        source["live"]["acknowledged_seq"]["a"] = 99
        self.assertEqual(guided_ui.card(source, STEPS, role="a").completed, 0)
        source["live"]["guided"] = progress(1)
        view = guided_ui.card(source, STEPS, role="b", available=True)
        self.assertEqual(view.completed, 1)
        self.assertEqual(view.checklist[0][2], "confirmed")
        self.assertTrue(view.enabled)

    def test_stale_malformed_or_mismatched_progress_cannot_check_steps(self):
        for change in ({"step_id": "wrong"}, {"step": 1}, {"index": 0},
                       {"index": True}, {"completed_steps": 2}, {"total_steps": 20},
                       {"completed_step_ids": ["unknown"]},
                       {"completed_step_ids": ["host_pause", "host_pause"]}):
            with self.subTest(change=change):
                source = status(1)
                source["live"]["guided"].update(change)
                view = guided_ui.card(source, STEPS, role="b", available=True)
                self.assertFalse(view.enabled)
                self.assertEqual(view.completed, 0)

    def test_terminal_and_pending_never_enable_actions(self):
        for change in ({"failure": "peer disconnected"}, {"stopping": True},
                       {"completed": True}, {"finish_requested": True}):
            source = status() | change
            self.assertFalse(guided_ui.card(source, STEPS, role="a", available=True).enabled)
        source = status()
        source["live"]["guided"]["pending"] = True
        self.assertFalse(guided_ui.card(source, STEPS, role="a", available=True).enabled)
        source["live"]["guided"]["pending"] = False
        self.assertFalse(guided_ui.card(source, STEPS, role="a", available=True, locally_pending=True).enabled)
        self.assertFalse(guided_ui.card(source, STEPS, role="a", available=False).enabled)

    def test_transport_completion_alone_does_not_complete_checklist(self):
        view = guided_ui.card(status() | {"completed": True}, STEPS, role="a", available=True)
        self.assertEqual(view.completed, 0)
        self.assertNotEqual(view.phase, "completed")
        complete = guided_ui.card(status(2), STEPS, role="a")
        self.assertEqual(complete.completed, 2)
        self.assertEqual(complete.phase, "completed")
        self.assertIsNone(complete.command)
        source = status(2)
        source["live"]["guided"]["phase"] = "pending"
        finishing = guided_ui.card(source, STEPS, role="a")
        self.assertEqual(finishing.completed, 2)
        self.assertEqual(finishing.phase, "finishing")
        self.assertNotIn("Aufbau", finishing.title)

    def test_failed_step_keeps_previous_confirmations_without_fabricated_next(self):
        source = status(1) | {"failure": "callback mismatch"}
        view = guided_ui.card(source, STEPS, role="b", available=True)
        self.assertEqual(view.completed, 1)
        self.assertEqual(view.phase, "halted")
        self.assertIsNone(view.command)
        self.assertNotIn("confirmed", [row[2] for row in view.checklist[1:]])

    def test_installed_catalog_is_presentable_for_both_players(self):
        from prototype.strict_sync.guided_catalog import STEPS as installed_steps
        for index, item in enumerate(installed_steps):
            source = {"guided": {"index": index, "step": item["step"], "step_id": item["id"],
                                  "completed_step_ids": [row["id"] for row in installed_steps[:index]],
                                  "phase": "ready"}}
            for role in ("a", "b"):
                with self.subTest(step=item["id"], role=role):
                    view = guided_ui.card(source, installed_steps, role=role, available=True)
                    self.assertEqual(view.enabled, role == item["actor"])
                    self.assertEqual(view.completed, index)
                    self.assertEqual(view.command, {"op": "GUIDED_ACTION", "step": index + 1})


class GuidedHandlerTests(unittest.TestCase):
    def setUp(self):
        self.app = launcher.App.__new__(launcher.App)
        self.app.prepared = SimpleNamespace(role="a", test_mode="guided_suite_v1")
        self.app.busy = False
        self.app.controller = Mock()
        self.source = status()
        self.app.controller.poll.side_effect = lambda: deepcopy(self.source)
        self.app.controller.submit_live.return_value = 7
        self.app.guided_pending_sequence = None
        self.app.guided_pending_revision = None
        self.app.guided_pending_index = None
        self.app.status = Mock()
        self.app._buttons = Mock()
        self.stack = []
        for context in (
            patch.dict("sys.modules", {"prototype.strict_sync.guided_catalog": SimpleNamespace(STEPS=STEPS)}),
            patch.object(launcher.workflow, "GUIDED_MODE", "guided_suite_v1", create=True),
            patch.object(launcher.workflow, "live_input_ready", return_value=True),
            patch.object(launcher.tk, "Tk", side_effect=AssertionError("No desktop windows")),
        ):
            context.start()
            self.addCleanup(context.stop)

    def test_double_click_with_old_poll_enqueues_only_once(self):
        self.app.submit_guided()
        self.app.submit_guided()
        self.app.controller.submit_live.assert_called_once_with({"op": "GUIDED_ACTION", "step": 1})
        self.assertEqual(self.app.guided_pending_sequence, 7)
        self.assertEqual(self.app.last_live_status["live"]["guided"]["completed_steps"], 0)

    def test_other_player_or_local_unsettled_progress_cannot_clear_latch(self):
        self.app.submit_guided()
        self.source["live"]["acknowledged_seq"]["b"] = 7
        self.app._update_guided_pending(self.source)
        self.assertEqual(self.app.guided_pending_sequence, 7)
        self.app._update_guided_pending({})
        self.assertEqual(self.app.guided_pending_sequence, 7)

    def test_settled_retry_can_unlock_same_step_without_checking_it_off(self):
        self.app.submit_guided()
        self.source["live"]["guided"]["settled_revision"] += 1
        self.source["live"]["guided"]["last_attempt"] = {"step": 1, "seq": 7, "peer": "a",
                                                               "status": "rejected", "reason": "not_ready"}
        self.app.submit_guided()
        self.assertEqual(self.app.controller.submit_live.call_count, 2)
        self.assertEqual(self.source["live"]["guided"]["completed_steps"], 0)

    def test_fresh_poll_that_changed_actor_prevents_old_display_click(self):
        self.source["live"]["guided"] = progress(1)
        self.app.submit_guided()
        self.app.controller.submit_live.assert_not_called()

    def test_failed_enqueue_does_not_mark_step_complete_or_latch(self):
        self.app.controller.submit_live.side_effect = ValueError("session not ready")
        self.app.submit_guided()
        self.assertIsNone(self.app.guided_pending_sequence)
        self.assertEqual(self.app.last_live_status["live"]["guided"]["completed_steps"], 0)

    def render_app(self):
        for name in ("guided_heading", "guided_instruction", "guided_actor", "guided_count", "connection_summary"):
            setattr(self.app, name, Value())
        for name in ("wizard_export_button", "wizard_stop_button", "wizard_save", "guided_progress_bar",
                     "wizard_prepare_button", "wizard_connect_button", "wizard_game_button", "guided_action_button"):
            setattr(self.app, name, Mock())
        self.app.wizard_buttons = (self.app.wizard_prepare_button, self.app.wizard_connect_button,
                                   self.app.wizard_game_button, self.app.guided_action_button)
        self.app.controller.alive.return_value = True
        self.app.host, self.app.code = Value("127.0.0.1"), Value("private fixture")
        self.app.last_run = self.app.diagnostic = None
        self.app.pairing_saved = self.app.baseline_ready = True
        self.app._render_checklist = Mock()
        self.app.last_live_status = deepcopy(self.source)
        return self.app

    def test_actual_card_render_wires_only_current_role_action(self):
        app = self.render_app()
        app._render_wizard()
        app.guided_action_button.configure.assert_called_with(state="normal")
        self.assertEqual(app.guided_actor.get(), "Host ist dran")
        for button in app.wizard_buttons[:3]:
            button.grid_remove.assert_called()
        app.prepared.role = "b"
        app._render_wizard()
        app.guided_action_button.configure.assert_called_with(state="disabled")

    def test_final_report_keeps_confirmed_checklist_when_live_progress_is_gone(self):
        app = self.render_app()
        app.last_live_status = {"completed": True, "live_result": {"guided": progress(2)}}
        app._render_wizard()
        self.assertEqual(app.guided_count.get(), "2 von 2 Schritten gemeinsam bestätigt")
        self.assertTrue(all(row[2] == "confirmed" for row in app._render_checklist.call_args.args[0]))

    def test_new_prepare_is_only_offered_after_old_controllers_have_stopped(self):
        app = self.render_app()
        app.last_live_status["failure"] = "fixture failure"
        app._render_wizard()
        app.wizard_prepare_button.configure.assert_any_call(state="disabled")
        app.wizard_prepare_button.grid.assert_not_called()
        app.controller.alive.return_value = False
        app._render_wizard()
        app.wizard_prepare_button.configure.assert_called_with(state="normal")


if __name__ == "__main__":
    unittest.main()
