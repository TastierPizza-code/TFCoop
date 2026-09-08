"""Last launcher workflow boundary before persistent guided queue submission."""
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from prototype.strict_sync import launcher_session as workflow
from prototype.strict_sync.guided_catalog import get_step


class GuidedSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.controller = workflow.SessionController(SimpleNamespace(
            test_mode=workflow.GUIDED_MODE, role='a'))
        self.writer = self.controller._input_writer = Mock()
        self.writer.submit.return_value = 1
        self.status = {'test_mode': workflow.GUIDED_MODE, 'peer_started': True,
                       'alive': True, 'failure': '', 'stopping': False,
                       'round': 10,
                       'live': {'started': True, 'confirmed_paused': False,
                                'acknowledged_seq': {'a': 0, 'b': 0}},
                       'guided': {'phase': 'ready', 'ready': True, 'pending': False, 'actor': 'a', 'step': 1}}
        self.controller.poll = Mock(return_value=self.status)

    def test_current_host_command_enqueues_once_until_its_receipt(self):
        command = get_step(1)['command']
        self.assertEqual(self.controller.submit_live(command), 1)
        with self.assertRaises(ValueError):
            self.controller.submit_live(command)
        self.writer.submit.assert_called_once_with(command)

    def test_role_phase_or_command_mismatch_never_writes(self):
        for field, value in (('actor', 'b'), ('phase', 'pending'), ('pending', True)):
            prior = self.status['guided'][field]
            self.status['guided'][field] = value
            with self.assertRaises(ValueError):
                self.controller.submit_live(get_step(1)['command'])
            self.status['guided'][field] = prior
        for command in (get_step(2)['command'], {'op': 'END_TEST'}, {'op': 'SET_PAUSED', 'value': True}):
            with self.assertRaises(ValueError):
                self.controller.submit_live(command)
        self.writer.submit.assert_not_called()

    def test_ended_session_does_not_accept_even_coherent_guide(self):
        self.status['completed'] = True
        with self.assertRaises(ValueError):
            self.controller.submit_live(get_step(1)['command'])
        self.writer.submit.assert_not_called()

    def test_no_first_action_before_joint_start_and_completed_preparation(self):
        for mapping, field, value in ((self.status, 'round', 0),
                                      (self.status, 'round', 9),
                                      (self.status['live'], 'started', False),
                                      (self.status['live'], 'confirmed_paused', None),
                                      (self.status['guided'], 'ready', False)):
            with self.subTest(field=field, value=value):
                prior = mapping[field]
                mapping[field] = value
                with self.assertRaises(ValueError):
                    self.controller.submit_live(get_step(1)['command'])
                mapping[field] = prior
        self.writer.submit.assert_not_called()

    def test_result_fallback_keeps_exact_final_guided_progress(self):
        value = {'phase': 'completed', 'completed_steps': 26}
        self.assertEqual(workflow.guided_status({'live_result': {'guided': value}}), value)


if __name__ == '__main__':
    unittest.main()
