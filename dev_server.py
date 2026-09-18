"""Development dashboard for browser-use — serves a status page on port 3000.

Uses only the Python standard library so it works before dependencies are installed.
The page shows installation status, version info, available CLI commands, examples,
and environment variable configuration.
"""

from __future__ import annotations

import html
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('DEV_SERVER_PORT', '3000'))


def _check_import() -> dict:
	"""Try importing browser_use and return status info."""
	try:
		import browser_use  # noqa: F401

		version = getattr(browser_use, '__version__', 'unknown')
		# Try getting version from importlib.metadata
		try:
			from importlib.metadata import version as get_version

			version = get_version('browser-use')
		except Exception:
			pass
		return {'installed': True, 'version': version, 'error': None}
	except Exception as e:
		return {'installed': False, 'version': None, 'error': str(e)}


def _get_env_status() -> list[dict]:
	"""Check which relevant environment variables are set (without revealing values)."""
	env_vars = [
		('BROWSER_USE_API_KEY', 'Browser Use Cloud API key (for ChatBrowserUse & cloud browsers)', True),
		('OPENAI_API_KEY', 'OpenAI API key (for ChatOpenAI)', False),
		('ANTHROPIC_API_KEY', 'Anthropic API key (for ChatAnthropic)', False),
		('GOOGLE_API_KEY', 'Google/Gemini API key (for ChatGoogle)', False),
		('DEEPSEEK_API_KEY', 'DeepSeek API key', False),
		('GROQ_API_KEY', 'Groq API key', False),
		('ANONYMIZED_TELEMETRY', 'Anonymous telemetry toggle', False),
		('BROWSER_USE_LOGGING_LEVEL', 'Logging level', False),
	]
	result = []
	for name, desc, important in env_vars:
		val = os.environ.get(name)
		result.append({
			'name': name,
			'description': desc,
			'important': important,
			'set': val is not None and val != '' and not val.startswith('your_'),
		})
	return result


def _get_examples() -> list[dict]:
	"""List example files."""
	examples_dir = REPO_ROOT / 'examples'
	examples = []
	if examples_dir.exists():
		for f in sorted(examples_dir.glob('*.py')):
			examples.append({'name': f.name, 'path': str(f.relative_to(REPO_ROOT))})
		# Also list getting_started examples
		gs_dir = examples_dir / 'getting_started'
		if gs_dir.exists():
			for f in sorted(gs_dir.glob('*.py')):
				examples.append({'name': f'getting_started/{f.name}', 'path': str(f.relative_to(REPO_ROOT))})
	return examples[:15]  # limit


def _get_cli_help() -> str:
	"""Try to get CLI help output."""
	try:
		result = subprocess.run(
			[sys.executable, '-m', 'browser_use', '--help'],
			capture_output=True,
			text=True,
			timeout=10,
			cwd=str(REPO_ROOT),
		)
		return result.stdout or result.stderr or '(no output)'
	except Exception as e:
		return f'(unable to get CLI help: {e})'


def _read_file_snippet(path: str, max_lines: int = 20) -> str:
	"""Read first N lines of a file."""
	try:
		full = REPO_ROOT / path
		lines = full.read_text().splitlines()[:max_lines]
		return '\n'.join(lines)
	except Exception:
		return '(unable to read file)'


# Cache for status data
_status_cache: dict | None = None
_status_lock = threading.Lock()


def _build_status() -> dict:
	global _status_cache
	with _status_lock:
		if _status_cache is not None:
			return _status_cache
		data = {
			'import_status': _check_import(),
			'env_status': _get_env_status(),
			'examples': _get_examples(),
			'python_version': sys.version,
			'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
		}
		_status_cache = data
		return data


def _render_html() -> str:
	status = _build_status()
	imp = status['import_status']
	env_vars = status['env_status']
	examples = status['examples']

	# Determine overall status
	installed = imp['installed']
	important_keys = [e for e in env_vars if e['important']]
	has_important_key = any(e['set'] for e in important_keys)

	overall_status = 'ready' if installed and has_important_key else ('installed' if installed else 'error')
	status_badge = {
		'ready': ('✅ Ready', '#22c55e'),
		'installed': ('⚠️ Installed — API key needed', '#f59e0b'),
		'error': ('❌ Import failed', '#ef4444'),
	}[overall_status]

	env_rows = '\n'.join(
		f'<tr class="{"important" if e["important"] else ""}">'
		f'<td><code>{html.escape(e["name"])}</code></td>'
		f'<td>{html.escape(e["description"])}</td>'
		f'<td><span class="badge {"badge-set" if e["set"] else "badge-unset"}">'
		f'{"✓ Set" if e["set"] else "✗ Not set"}</span></td>'
		f'</tr>'
		for e in env_vars
	)

	example_rows = '\n'.join(
		f'<li><code>uv run {html.escape(e["path"])}</code></li>'
		for e in examples
	) or '<li>No examples found</li>'

	version_str = html.escape(imp['version'] or 'unknown')
	error_str = html.escape(imp['error'] or '')
	py_version = html.escape(status['python_version'].split()[0] + ' ' + ' '.join(status['python_version'].split()[1:4]))

	return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Browser Use — Dev Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f0f0f; color: #e0e0e0; line-height: 1.6; min-height: 100vh;
  }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem; }}
  header {{ text-align: center; margin-bottom: 2.5rem; }}
  .logo {{
    font-size: 2.5rem; font-weight: 800; letter-spacing: -0.03em;
    background: linear-gradient(135deg, #f97316, #fb923c); -webkit-background-clip: text;
    -webkit-text-fill-color: transparent; margin-bottom: 0.25rem;
  }}
  .tagline {{ color: #888; font-size: 1.05rem; }}
  .status-badge {{
    display: inline-block; padding: 0.5rem 1.25rem; border-radius: 999px;
    font-weight: 600; font-size: 0.95rem; margin-top: 1rem;
    background: {status_badge[1]}22; color: {status_badge[1]}; border: 1px solid {status_badge[1]}55;
  }}
  .card {{
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
    padding: 1.5rem; margin-bottom: 1.5rem;
  }}
  .card h2 {{
    font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem;
    color: #f97316; display: flex; align-items: center; gap: 0.5rem;
  }}
  .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
  .info-item {{ background: #222; border-radius: 8px; padding: 0.85rem 1rem; }}
  .info-label {{ color: #888; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .info-value {{ color: #e0e0e0; font-size: 0.95rem; margin-top: 0.2rem; font-family: monospace; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; color: #888; font-size: 0.8rem; text-transform: uppercase; padding: 0.5rem; border-bottom: 1px solid #2a2a2a; }}
  td {{ padding: 0.6rem 0.5rem; border-bottom: 1px solid #222; font-size: 0.9rem; }}
  tr.important td:first-child {{ color: #f97316; font-weight: 600; }}
  .badge {{ padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }}
  .badge-set {{ background: #22c55e22; color: #4ade80; }}
  .badge-unset {{ background: #ef444422; color: #f87171; }}
  ul {{ list-style: none; }}
  ul li {{ padding: 0.4rem 0; color: #ccc; }}
  code {{ background: #2a2a2a; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.88em; color: #fb923c; }}
  .error-box {{ background: #ef444422; border: 1px solid #ef444455; border-radius: 8px; padding: 1rem; margin-top: 1rem; font-family: monospace; font-size: 0.85rem; color: #f87171; white-space: pre-wrap; }}
  .footer {{ text-align: center; color: #555; font-size: 0.85rem; margin-top: 2rem; }}
  .footer a {{ color: #f97316; text-decoration: none; }}
  .actions {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }}
  .action-btn {{
    display: inline-block; padding: 0.5rem 1rem; border-radius: 8px;
    background: #2a2a2a; color: #e0e0e0; text-decoration: none; font-size: 0.9rem;
    border: 1px solid #3a3a3a; transition: border-color 0.2s;
  }}
  .action-btn:hover {{ border-color: #f97316; }}
  .code-block {{
    background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 1rem; margin-top: 0.75rem; overflow-x: auto;
    font-family: 'SF Mono', Monaco, monospace; font-size: 0.85rem; color: #ccc;
    white-space: pre; line-height: 1.5;
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">Browser Use</div>
    <div class="tagline">Make websites accessible for AI agents</div>
    <div class="status-badge">{status_badge[0]}</div>
  </header>

  <div class="card">
    <h2>📦 Installation Status</h2>
    <div class="info-grid">
      <div class="info-item">
        <div class="info-label">Library</div>
        <div class="info-value">{"✅ Installed" if installed else "❌ Not installed"}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Version</div>
        <div class="info-value">{version_str}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Python</div>
        <div class="info-value">{py_version}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Last Checked</div>
        <div class="info-value">{html.escape(status["timestamp"])}</div>
      </div>
    </div>
    {f'<div class="error-box">{error_str}</div>' if error_str else ''}
  </div>

  <div class="card">
    <h2>🔑 Environment Variables</h2>
    <table>
      <thead><tr><th>Variable</th><th>Description</th><th>Status</th></tr></thead>
      <tbody>{env_rows}</tbody>
    </table>
    <div class="actions">
      <a class="action-btn" href="https://cloud.browser-use.com/new-api-key" target="_blank">Get BROWSER_USE_API_KEY →</a>
      <a class="action-btn" href="https://platform.openai.com/api-keys" target="_blank">Get OPENAI_API_KEY →</a>
    </div>
  </div>

  <div class="card">
    <h2>🚀 Quick Start</h2>
    <div class="code-block">from browser_use import Agent, ChatBrowserUse

agent = Agent(
    task="Find the number of stars of the browser-use repo",
    llm=ChatBrowserUse(model="bu-2-0"),
)
agent.run_sync()</div>
    <div class="actions">
      <a class="action-btn" href="https://docs.browser-use.com" target="_blank">📖 Documentation</a>
      <a class="action-btn" href="https://github.com/browser-use/browser-use" target="_blank">🐙 GitHub</a>
    </div>
  </div>

  <div class="card">
    <h2>📋 Available Examples</h2>
    <ul>{example_rows}</ul>
  </div>

  <div class="card">
    <h2>💻 CLI Commands</h2>
    <div class="code-block">browser-use                    # Interactive CLI (pipe Python on stdin)
browser-use install            # Install Chromium + system deps
browser-use init               # Generate a new project from template
browser-use --mcp              # Run as MCP server
browser-use --cli-mcp          # Run as CLI MCP server
browser-use skill install      # Install the browser-use skill
browser-use --doctor           # Check install health</div>
  </div>

  <div class="footer">
    Browser Use v{version_str} — <a href="https://docs.browser-use.com">docs.browser-use.com</a> —
    Dashboard refreshed at {html.escape(status["timestamp"])}
  </div>
</div>
</body>
</html>'''


class DashboardHandler(http.server.BaseHTTPRequestHandler):
	protocol_version = 'HTTP/1.1'

	def _send_html(self):
		html_content = _render_html()
		body = html_content.encode('utf-8')
		self.send_response(200)
		self.send_header('Content-Type', 'text/html; charset=utf-8')
		self.send_header('Content-Length', str(len(body)))
		self.send_header('Connection', 'close')
		self.end_headers()
		if self.command == 'GET':
			self.wfile.write(body)

	def _send_json(self):
		data = json.dumps(_build_status(), indent=2).encode()
		self.send_response(200)
		self.send_header('Content-Type', 'application/json')
		self.send_header('Content-Length', str(len(data)))
		self.send_header('Connection', 'close')
		self.end_headers()
		if self.command == 'GET':
			self.wfile.write(data)

	def _send_health(self):
		body = b'ok'
		self.send_response(200)
		self.send_header('Content-Type', 'text/plain')
		self.send_header('Content-Length', str(len(body)))
		self.send_header('Connection', 'close')
		self.end_headers()
		if self.command == 'GET':
			self.wfile.write(body)

	def _send_404(self):
		self.send_response(404)
		self.send_header('Content-Length', '0')
		self.send_header('Connection', 'close')
		self.end_headers()

	def _route(self):
		from urllib.parse import urlsplit

		return urlsplit(self.path).path

	def do_GET(self):
		path = self._route()
		if path in ('/', '/index.html'):
			self._send_html()
		elif path == '/api/status':
			self._send_json()
		elif path == '/health':
			self._send_health()
		else:
			self._send_404()

	def do_HEAD(self):
		path = self._route()
		if path in ('/', '/index.html'):
			self._send_html()
		elif path == '/api/status':
			self._send_json()
		elif path == '/health':
			self._send_health()
		else:
			self._send_404()

	def log_message(self, fmt, *args):
		print(f'[dashboard] {args[0]}')


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
	daemon_threads = True


def main():
	print(f'[dashboard] Browser Use dev dashboard starting on port {PORT}...')
	print(f'[dashboard] Python: {sys.version}')
	# Build initial status
	_build_status()
	server = ThreadingHTTPServer(('0.0.0.0', PORT), DashboardHandler)
	print(f'[dashboard] Serving at http://0.0.0.0:{PORT}')
	server.serve_forever()


if __name__ == '__main__':
	main()
