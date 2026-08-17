/**
 * Thin client shared by start_dialog_temperature_swing.html and
 * temperature_swing_progress.html. Talks to the three FastAPI routes and
 * the WebSocket status stream described in ../backend/README.md.
 */
const TemperatureSwingClient = (() => {
  const API_BASE = '/api/temperature-swing';
  let socket = null;
  let updateHandler = null;
  let completeHandler = null;

  function connectSocket() {
    if (socket && socket.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${protocol}://${window.location.host}/ws/temperature-swing`);

    socket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === 'temperature_swing_update' && updateHandler) {
        updateHandler(payload);
      } else if (payload.type === 'temperature_swing_complete' && completeHandler) {
        completeHandler();
      }
    });

    socket.addEventListener('close', () => {
      // Reconnect after a short delay if the progress page is still open
      setTimeout(connectSocket, 2000);
    });
  }

  async function startTest({ extremeTempC, pressureMode, holdMinutes }) {
    const response = await fetch(`${API_BASE}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        extreme_temp_c: extremeTempC,
        pressure_mode: pressureMode,
        hold_duration_min: holdMinutes,
      }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  async function stopTest() {
    const response = await fetch(`${API_BASE}/stop`, { method: 'POST' });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  }

  function onUpdate(handler) {
    updateHandler = handler;
    connectSocket();
  }

  function onComplete(handler) {
    completeHandler = handler;
    connectSocket();
  }

  return { startTest, stopTest, onUpdate, onComplete };
})();
