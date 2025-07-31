import streamlit as st
import streamlit.components.v1 as components
import os
from dotenv import load_dotenv

load_dotenv()

api_base = os.getenv("API_BASE_URL")
ws_endpoint = os.getenv("WS_STREAM_ENDPOINT")

st.set_page_config(page_title="Live Medical Transcription", layout="wide")
st.title("📝 Live Medical Transcription via Mic (AWS Transcribe Medical)")
st.write("→ connecting to:", ws_endpoint, api_base)

st.markdown("""
Use the button below to start recording your voice. Your audio will be streamed to AWS Transcribe Medical in real time.

Ensure your mic is enabled and you are using a Chromium-based browser for full support.
""")

components.html(fr"""
<html>
  <head>
    <style>
      #status {{ font-weight: bold; }}
      .idle {{ color: gray; }}
      .connecting {{ color: orange; }}
      .recording {{ color: green; }}
      .finishing {{ color: DodgerBlue; }}
      .done {{ color: green; }}
      .error {{ color: red; }}
    </style>
  </head>
  <body>
    <button id="record">Start Recording</button>
    <button id="stop" disabled>Stop Recording</button>
    <button id="pause" style="display: none;">Pause</button>
    <button id="clear">Clear Transcript</button>
    <button id="copy">Copy</button>
    <span id="copy-notification" style="color: green; font-weight: bold; display: none; margin-left: 10px;">Copied!</span>
    <button id="save" style="display: none;">Save</button>
    <span id="save-notification" style="color: green; font-weight: bold; display: none; margin-left: 10px;">Saved!</span>
    <p id="status" class="idle">Status: Idle</p>
    <textarea id="transcript"
      style="
        width: 100%;
        height: 200px;
        border: 1px solid #ddd;
        background-color: #1e1e1e;
        color: #d4d4d4;
        font-family: Consolas, 'Courier New', monospace;
        padding: 10px;
        font-size: 16px;
        box-shadow: 0 0 5px rgba(0,0,0,0.7);
        resize: vertical;
      "
    ></textarea>

    <script>
      let ws;
      const WS_ENDPOINT = "{ws_endpoint}";
      const API_BASE   = "{api_base}";

      let audioContext, source, processor, stream;
      let lastSent = Date.now();
      let keepAlive;
      let isRecording = false;
      let isPaused    = false;

      function $(id) {{ return document.getElementById(id); }}

      function setStatus(text, className) {{
        const statusEl = $("status");
        statusEl.innerText  = text;
        statusEl.className  = className;
      }}

      function showNotification(id, duration = 2000) {{
        const notif = $(id);
        notif.style.display = "inline";
        setTimeout(() => notif.style.display = "none", duration);
      }}

      function toggleSaveButton() {{
        $("save").style.display = $("transcript").value.trim() ? "inline" : "none";
      }}

      function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {{
        if (outputSampleRate === inputSampleRate) return buffer;
        const ratio = inputSampleRate / outputSampleRate;
        const newLen = Math.round(buffer.length / ratio);
        const result = new Int16Array(newLen);
        for (let i = 0; i < newLen; i++) {{
          const start = Math.floor(i * ratio);
          const end   = Math.floor((i + 1) * ratio);
          let sum = 0, count = 0;
          for (let j = start; j < end && j < buffer.length; j++) {{
            sum += buffer[j];
            count++;
          }}
          const avg = sum / count;
          const s   = Math.max(-1, Math.min(1, avg));
          result[i] = Math.round(s < 0 ? s * 0x8000 : s * 0x7FFF);
        }}
        return result;
      }}

      function convertFloat32ToInt16(buffer) {{
        return Int16Array.from(buffer, s => {{
          const clamped = Math.max(-1, Math.min(1, s));
          return Math.round(clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF);
        }});
      }}

      async function startRecording() {{
        $("transcript").value = "";
        stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
        setStatus("Status: Connecting to server...", "connecting");

        ws = new WebSocket(WS_ENDPOINT);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {{
          isRecording = true;
          setStatus("Status: Recording and streaming audio...", "recording");
          $("pause").style.display = "inline";
          audioContext = new (window.AudioContext || window.webkitAudioContext)();
          source       = audioContext.createMediaStreamSource(stream);
          processor    = audioContext.createScriptProcessor(2048, 1, 1);

          source.connect(processor);
          processor.connect(audioContext.destination);

          processor.onaudioprocess = (e) => {{
            const input = e.inputBuffer.getChannelData(0);
            const data  = (audioContext.sampleRate === 48000)
              ? convertFloat32ToInt16(input)
              : downsampleBuffer(input, audioContext.sampleRate, 48000);
            if (ws.readyState === 1) {{
              ws.send(data.buffer);
              lastSent = Date.now();
            }}
          }};

          keepAlive = setInterval(() => {{
            if (ws.readyState === 1 && Date.now() - lastSent > 5000) {{
              ws.send(new Int16Array(2048).buffer);
              lastSent = Date.now();
            }}
          }}, 5000);
        }};

        ws.onmessage = handleTranscriptMessage;
        ws.onclose   = cleanupRecording;
        ws.onerror   = (event) => {{
          console.error("WebSocket error:", event);
          setStatus("WebSocket error occurred", "error");
          $("transcript").value += "[WebSocket error]\n";
        }};
      }}

      function handleTranscriptMessage(event) {{
        try {{
          const parsed = JSON.parse(event.data);
          if (parsed.ErrorMessage || parsed.error) {{
            setStatus("Error from server: " + (parsed.ErrorMessage || parsed.error), "error");
            return;
          }}

          const results = parsed.TranscriptEvent?.Transcript?.Results || [];
          results.forEach(result => {{
            if (!result.IsPartial && result.Alternatives.length > 0) {{
              const line = result.Alternatives[0].Transcript;
              $("transcript").value += line + "\n";
              $("transcript").scrollTop = $("transcript").scrollHeight;
            }}
          }});

          if (isRecording && !isPaused) {{
            setStatus("Status: Recording and streaming audio...", "recording");
          }}
        }} catch {{
          setStatus("Error: Invalid server response", "error");
          $("transcript").value += "[Error] " + event.data + "\n";
        }}
      }}

      function cleanupRecording() {{
        setStatus("Status: Done", "done");
        processor?.disconnect();
        processor.onaudioprocess = null;
        source?.disconnect();
        audioContext?.close();
        stream?.getTracks().forEach(t => t.stop());
        clearInterval(keepAlive);
      }}

      function stopRecording() {{
        if (ws?.readyState === WebSocket.OPEN) ws.send(new ArrayBuffer(0));
        isRecording = false;
        setStatus("Status: Finishing transcription...", "finishing");
        $("stop").disabled = true;
        $("record").disabled = false;
        $("save").style.display = "inline";
        $("pause").style.display = "none";
        $("pause").innerText = "Pause";
        isPaused = false;
      }}

      function togglePauseResume() {{
        if (!audioContext || !processor) return;
        if (isPaused) {{
          processor.connect(audioContext.destination);
          source.connect(processor);
          setStatus("Status: Recording and streaming audio...", "recording");
          $("pause").innerText = "Pause";
        }} else {{
          processor.disconnect(audioContext.destination);
          source.disconnect(processor);
          setStatus("Status: Paused", "idle");
          $("pause").innerText = "Resume";
        }}
        isPaused = !isPaused;
        $("save").style.display = "none";
      }}

      function clearTranscript() {{ $("transcript").value = ""; toggleSaveButton(); }}

      function copyTranscript() {{
        const text = $("transcript").value;
        if (!text) return alert("Transcript is empty!");
        navigator.clipboard.writeText(text)
          .then(() => showNotification("copy-notification"))
          .catch(err => alert("Failed to copy: " + err));
      }}

      function saveTranscript() {{
        const transcript = $("transcript").value.trim();
        if (!transcript) return alert("Transcript is empty!");
        fetch(`${{API_BASE}}/api/save`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ transcript }})
        }})
          .then(res => res.json())
          .then(data => {{
            alert("✅ " + data.message);
            $("save").style.display = "none";
          }})
          .catch(err => {{
            console.error("❌ Error saving:", err);
            alert("Failed to save transcript.");
          }});
      }}

      function initUIEvents() {{
        $("record").onclick = () => {{ $("record").disabled = true; $("stop").disabled = false; $("save").style.display = "none"; $("pause").style.display = "none"; startRecording(); }};
        $("stop").onclick   = stopRecording;
        $("pause").onclick  = togglePauseResume;
        $("clear").onclick  = clearTranscript;
        $("copy").onclick   = copyTranscript;
        $("save").onclick   = saveTranscript;
        $("transcript").oninput = toggleSaveButton;
      }}

      window.onload = initUIEvents;
    </script>
  </body>
</html>
""", height=300)

st.markdown("""
Once you click **Start Recording**, your voice will be captured and streamed live.  
**Stop Recording** will send an “end-of-stream (EOS),” then transcripts will appear in the box as they are finalized.
""")
