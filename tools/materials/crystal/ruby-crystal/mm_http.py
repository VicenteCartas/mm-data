"""mm_http.py: a minimal client for Material Maker's built-in MCP (Streamable HTTP, JSON responses, 127.0.0.1:8790)."""
import json
import urllib.request

URL = 'http://127.0.0.1:8790/mcp'


class Client:
    def __init__(self, name='claude-session-d0e2b282'):
        self.sid, self.next_id = None, 1
        init = self._post('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                         'clientInfo': {'name': name, 'version': '1'}})
        self.server = init['result']['serverInfo']
        self._post('notifications/initialized', notify=True)

    def _post(self, method, params=None, notify=False, timeout=60):
        body = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        if not notify:
            body['id'] = self.next_id
            self.next_id += 1
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self.sid:
            headers['Mcp-Session-Id'] = self.sid
        request = urllib.request.Request(URL, json.dumps(body).encode(), headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            self.sid = response.headers.get('Mcp-Session-Id') or self.sid
            text = response.read().decode()
        return json.loads(text) if text.strip() else None

    def tools(self):
        return self._post('tools/list')['result']['tools']

    def call(self, name, timeout=600, **arguments):
        result = self._post('tools/call', {'name': name, 'arguments': arguments}, timeout=timeout)
        if 'error' in result:
            raise RuntimeError(result['error'])
        content = result['result']
        text = ''.join(c.get('text', '') for c in content.get('content', []) if c.get('type') == 'text')
        try:
            return json.loads(text)
        except ValueError:
            return content.get('structuredContent') or text
