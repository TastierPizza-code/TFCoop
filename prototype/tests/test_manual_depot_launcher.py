"""Actual headless launcher handlers and settled outcome presentation."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from prototype import launcher
from prototype.strict_sync import launcher_session as workflow, test_pairing
from prototype.tests.test_update_startup import headless_app, Value


class ManualDepotLauncherTests(unittest.TestCase):
    def app(self):
        app = headless_app()
        app.busy = False
        app.code = Value('1234-' * 7 + '1234')
        app.role = Value('a')
        app.depot_site, app.depot_rotation = Value('2'), Value('90')
        app.depot_button = Mock()
        app.depot_choices = (Mock(), Mock())
        return app

    def test_handler_enqueues_selected_place_and_rotation_without_game_input(self):
        app = self.app()
        app.submit_live = Mock()
        app.submit_depot()
        app.submit_live.assert_called_once_with({'op': 'BUILD_DEPOT', 'site': 2, 'rotation': 90})
        app.depot_site.set('bad')
        with patch.object(launcher.messagebox, 'showerror') as error:
            app.submit_depot()
        error.assert_called_once()
        self.assertEqual(app.submit_live.call_count, 1)

    def test_depot_controls_require_new_mode_and_ready_joint_input(self):
        app = self.app()
        app.controller = Mock()
        app.controller.alive.return_value = True
        ready = {'test_mode': workflow.MANUAL_DEPOT_MODE, 'peer_started': True, 'alive': True,
                 'live': {'started': True}, 'failure': '', 'stopping': False}
        app.last_live_status = ready
        app._buttons()
        app.depot_button.configure.assert_called_with(state='normal')
        for mode in (workflow.PACED_LIVE_MODE, workflow.STREAM_MODE):
            ready['test_mode'] = mode
            app._buttons()
            app.depot_button.configure.assert_called_with(state='disabled')
        ready['test_mode'] = workflow.MANUAL_DEPOT_MODE
        ready['finish_requested'] = True
        app._buttons()
        app.depot_button.configure.assert_called_with(state='disabled')

    def test_local_or_other_peer_receipt_does_not_claim_own_depot_built(self):
        status = {'test_mode': workflow.MANUAL_DEPOT_MODE, 'role': 'a', 'submitted_seq': 1,
                  'live': {'started': True, 'confirmed_paused': False, 'acknowledged_seq': {'a': 0},
                           'acknowledgements': [{'peer': 'b', 'seq': 1, 'command': {'op': 'BUILD_DEPOT', 'site': 2},
                                                 'status': 'applied', 'cost': 10}]}}
        text = workflow.live_input_status(status)
        self.assertIn('Noch 1 zur Bestätigung offen', text)
        self.assertNotIn('beidseitig gebaut', text)
        status['live']['acknowledgements'][0]['peer'] = 'a'
        status['live']['acknowledged_seq']['a'] = 1
        self.assertIn('Platz 2 beidseitig gebaut', workflow.live_input_status(status))
        result = status['live']['acknowledgements'][0]
        result.update(status='rejected', reason='site_occupied', cost=0)
        text = workflow.live_input_status(status)
        self.assertIn('Platz bereits belegt', text)
        self.assertIn('Keine Baukosten', text)

    def test_prepare_persists_private_profile_before_workflow(self):
        app = self.app()
        app.game.set('game fixture')
        app.saves.set('save fixture')
        app.host.set('127.0.0.1')
        app.test_mode = Value(workflow.MANUAL_DEPOT_MODE)
        app._work = Mock()
        app.prepare()
        job = app._work.call_args.args[0]
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(workflow, 'local_root', return_value=Path(temporary)), \
             patch.object(launcher.diagnostics, 'diagnostic_status', return_value={}), \
             patch.object(workflow, 'prepare', return_value='prepared') as prepare:
            self.assertEqual(job(), 'prepared')
            profile = test_pairing.load_profile(temporary)
        self.assertEqual(profile['host'], '127.0.0.1')
        self.assertEqual(profile['code'], app.code.get())
        self.assertEqual(prepare.call_args.kwargs['test_mode'], workflow.MANUAL_DEPOT_MODE)

    def test_discovery_keeps_private_host_and_restore_keeps_code(self):
        app = self.app()
        app.host.set('127.0.0.2')
        app.last_diagnostic = None
        with patch.object(launcher.sys, 'frozen', False, create=True):
            app._discovered((None, [], ['127.0.0.3'], None, None))
        self.assertEqual(app.host.get(), '127.0.0.2')
        for name in ('network', 'engine', 'progress_text'):
            setattr(app, name, Value())
        app.bar, app.game_button = {}, Mock()
        app._restored({})
        self.assertEqual(app.code.get(), '1234-' * 7 + '1234')
        self.assertEqual(app.host.get(), '127.0.0.2')

    def test_partial_completion_is_not_full_depot_coverage(self):
        status = {'test_mode': workflow.MANUAL_DEPOT_MODE, 'completed': True, 'failure': '',
                  'live_result': {'required_interactions_met': False}}
        self.assertIn('Nicht alle', workflow.describe_status(status))
        status['live_result']['required_interactions_met'] = True
        self.assertIn('Belegungsablehnung', workflow.describe_status(status))


if __name__ == '__main__':
    unittest.main()
