import json
import os
import subprocess
import sys
import tempfile
import unittest

BIN = os.path.join(os.path.dirname(__file__), '..', 'bin', 'transcript')
SID = '11111111-2222-3333-4444-555555555555'
CODEX_SID = '01a1e138-2dbd-7971-b4cd-b00000000001'
COPILOT_SID = '95c8e34d-86ff-4f59-8ceb-b5d1a816a3e2'


def jsonl(path, rows):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, 'w') as f:
		f.writelines(json.dumps(r) + '\n' for r in rows)


class Transcript(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		d = cls.d = tempfile.mkdtemp()
		t = '2026-11-20T10:00:00.000Z'
		jsonl(
			f'{d}/claude/projects/-work/{SID}.jsonl',
			[
				{
					'type': 'user',
					'timestamp': t,
					'cwd': '/work',
					'message': {'role': 'user', 'content': 'deploy the site'},
				},
				{
					'type': 'user',
					'timestamp': t,
					'message': {'role': 'user', 'content': '<system-reminder>noise deploy</system-reminder>'},
				},
				{
					'type': 'assistant',
					'timestamp': t,
					'message': {
						'role': 'assistant',
						'content': [
							{'type': 'text', 'text': 'Deploying now.'},
							{
								'type': 'tool_use',
								'id': 'a',
								'name': 'Bash',
								'input': {'command': 'rsync site/ host:/srv'},
							},
						],
					},
				},
				{
					'type': 'user',
					'timestamp': t,
					'message': {
						'role': 'user',
						'content': [{'type': 'tool_result', 'tool_use_id': 'a', 'content': 'sent 12 files'}],
					},
				},
			],
		)
		jsonl(
			f'{d}/codex/sessions/2026/11/20/rollout-2026-11-20T10-00-00-{CODEX_SID}.jsonl',
			[
				{'timestamp': t, 'type': 'session_meta', 'payload': {'id': CODEX_SID, 'cwd': '/repo'}},
				{
					'timestamp': t,
					'type': 'response_item',
					'payload': {
						'type': 'message',
						'role': 'user',
						'content': [{'type': 'input_text', 'text': 'review the parser'}],
					},
				},
				{
					'timestamp': t,
					'type': 'response_item',
					'payload': {
						'type': 'custom_tool_call',
						'name': 'exec',
						'input': 'tools.exec_command({cmd:"cargo test"})',
					},
				},
			],
		)
		jsonl(
			f'{d}/copilot/session-state/{COPILOT_SID}/events.jsonl',
			[
				{'type': 'session.start', 'timestamp': t, 'data': {'context': {'cwd': '/site'}}},
				{'type': 'user.message', 'timestamp': t, 'data': {'content': 'fix the navbar'}},
				{
					'type': 'tool.execution_start',
					'timestamp': t,
					'data': {'toolName': 'bash', 'arguments': {'command': 'npm test'}},
				},
			],
		)

	def run_t(self, *args):
		env = {
			**os.environ,
			'CLAUDE_CONFIG_DIR': f'{self.d}/claude',
			'CODEX_HOME': f'{self.d}/codex',
			'COPILOT_HOME': f'{self.d}/copilot',
		}
		env.pop('CLAUDE_CODE_SESSION_ID', None)
		return subprocess.run([sys.executable, BIN, *args], capture_output=True, text=True, env=env, check=False)

	def test_sessions_all_agents(self):
		out = self.run_t('sessions').stdout
		for want in ('claude', 'codex', 'copilot', 'deploy the site', 'review the parser', 'fix the navbar', '/repo'):
			self.assertIn(want, out)

	def test_find_skips_injected_context(self):
		out = self.run_t('find', 'deploy', '--role', 'user').stdout
		self.assertIn('deploy the site', out)
		self.assertNotIn('noise', out)

	def test_find_tool_and_result(self):
		self.assertIn('rsync site/', self.run_t('find', 'rsync', '--role', 'tool').stdout)
		self.assertIn('sent 12 files', self.run_t('find', 'sent', '--role', 'result').stdout)
		self.assertIn('cargo test', self.run_t('find', 'cargo', '-a', 'codex').stdout)
		self.assertEqual(self.run_t('find', 'nothing-like-this').returncode, 1)

	def test_show_and_tools_by_prefix(self):
		out = self.run_t('show', SID[:8]).stdout
		self.assertIn('Deploying now.', out)
		full = self.run_t('tools', COPILOT_SID[:6], '--full').stdout
		self.assertIn('--- command\nnpm test', full)
		self.assertIn('no session', self.run_t('show', 'ffffffff').stderr)


if __name__ == '__main__':
	unittest.main()
