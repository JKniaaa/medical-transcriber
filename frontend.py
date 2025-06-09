import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Live Medical Transcription", layout="wide")
st.title("Live Medical Transcription via Mic (AWS Transcribe Medical)")

st.markdown("""
Use the button below to start recording your voice. Your audio will be streamed to AWS Transcribe Medical in real time.

Ensure your mic is enabled and you are using a Chromium-based browser for full support.
""")

components.html(r"""
<html>
  <head>
    <style>
      #status {
        font-weight: bold;
      }
      .idle {
        color: gray;
      }
      .connecting {
        color: orange;
      }
      .recording {
        color: green;
      }
      .finishing {
        color: DodgerBlue;
      }
      .done {
        color: green;
      }
				
			.error {
				color: red;
			}
    </style>
  </head>
  <body>
    <button id="record">Start Recording</button>
    <button id="stop" disabled>Stop Recording</button>
    <button id="clear">Clear Transcript</button>
		<button id="copy">Copy</button>
    <span id="copy-notification" style="color: green; font-weight: bold; display: none; margin-left: 10px;">Copied!</span>
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
      let audioContext, source, processor, stream;
      let lastSent = Date.now();
      let keepAlive;

      function setStatus(text, className) {
        const statusEl = document.getElementById("status");
        statusEl.innerText = text;
        statusEl.className = className;
      }
                
      function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
        if (outputSampleRate === inputSampleRate) return buffer;

        const sampleRateRatio = inputSampleRate / outputSampleRate;
        const newLength = Math.round(buffer.length / sampleRateRatio);
        const result = new Int16Array(newLength);

        for (let i = 0; i < newLength; i++) {
          const start = Math.floor(i * sampleRateRatio);
          const end = Math.floor((i + 1) * sampleRateRatio);
          let sum = 0;
          let count = 0;

          for (let j = start; j < end && j < buffer.length; j++) {
            sum += buffer[j];
            count++;
          }

          const avg = sum / count;
          const s = Math.max(-1, Math.min(1, avg));
          result[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        return result;
      }

      function convertFloat32ToInt16(buffer) {
        let l = buffer.length;
        let buf = new Int16Array(l);
        while (l--) {
          let s = Math.max(-1, Math.min(1, buffer[l]));
          buf[l] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          buf[l] = Math.round(buf[l]);
        }
        return buf;
      }

      async function start() {
        // Clear transcript box on new recording
        document.getElementById("transcript").value = "";

        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setStatus("Status: Connecting to server...", "connecting");

        ws = new WebSocket("ws://localhost:3000/api/stream");
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
          setStatus("Status: Recording and streaming audio...", "recording");
          audioContext = new (window.AudioContext || window.webkitAudioContext)();
          source = audioContext.createMediaStreamSource(stream);
          processor = audioContext.createScriptProcessor(2048, 1, 1);
          console.log("AudioContext sample rate:", audioContext.sampleRate);

          source.connect(processor);
          processor.connect(audioContext.destination);

          processor.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            const downsampled = (audioContext.sampleRate === 48000) 
              ? convertFloat32ToInt16(inputData) 
              : downsampleBuffer(inputData, audioContext.sampleRate, 48000);
            if (ws.readyState === 1) {
              ws.send(downsampled.buffer);
              lastSent = Date.now();
            }
          };

          keepAlive = setInterval(() => {
            if (ws.readyState === 1 && Date.now() - lastSent > 5000) {
              let silent = new Int16Array(2048).buffer;
              ws.send(silent);
              lastSent = Date.now();
            }
          }, 5000);
        };

        ws.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data);

            // Check if backend sent an error object or message
            if (parsed.ErrorMessage || parsed.error) {
              const errorMsg = parsed.ErrorMessage || parsed.error;
              setStatus("Error from server: " + errorMsg, "error");
              return;
            }

            const results = parsed.TranscriptEvent?.Transcript?.Results || [];
            console.log("Message from server:", event.data);
            console.log("Transcript results:", results);

            results.forEach(result => {
              if (!result.IsPartial && result.Alternatives.length > 0) {
                const transcriptText = result.Alternatives[0].Transcript;
                const transcriptBox = document.getElementById("transcript");
                transcriptBox.value += transcriptText + "\n";
                transcriptBox.scrollTop = transcriptBox.scrollHeight;
              }
            });

            // If no errors, clear error status (optional)
            setStatus("Status: Recording and streaming audio...", "recording");

          } catch (e) {
            // JSON parse failed: show error status and append raw data to transcript
            setStatus("Error: Invalid server response", "error");
            document.getElementById("transcript").value += "[Error] " + event.data + "\n";
          }
        };

        ws.onclose = () => {
				  console.log("WebSocket closed:", event);
          setStatus("Status: Done", "done");
          if (processor) {
            processor.disconnect();
            processor.onaudioprocess = null;
          }
          if (source) source.disconnect();
          if (audioContext) audioContext.close();
          if (stream) stream.getTracks().forEach(t => t.stop());
          clearInterval(keepAlive);
        };
				
        ws.onerror = (event) => {
          console.error("WebSocket error:", event);
          setStatus("WebSocket error occurred", "error");
          document.getElementById("transcript").value += "[WebSocket error]\n";
        };

        document.getElementById("stop").onclick = () => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(new ArrayBuffer(0));
          }
          setStatus("Status: Finishing transcription...", "finishing");
          document.getElementById("stop").disabled = true;
          document.getElementById("record").disabled = false;
        };
      }

      document.getElementById("record").onclick = () => {
        document.getElementById("record").disabled = true;
        document.getElementById("stop").disabled = false;
        start();
      };
				
      document.getElementById("clear").onclick = () => {
        document.getElementById("transcript").value = "";
      };
				
			document.getElementById("copy").onclick = () => {
        const transcriptBox = document.getElementById("transcript");
        const text = transcriptBox.value;
        if (!text) {
          alert("Transcript is empty!");
          return;
        }
        navigator.clipboard.writeText(text).then(() => {
          const notif = document.getElementById("copy-notification");
          notif.style.display = "inline";
          setTimeout(() => {
            notif.style.display = "none";
          }, 2000);
        }).catch(err => {
          alert("Failed to copy: " + err);
        });
      };

    </script>
  </body>
</html>
""", height=500)

st.markdown("""
Once you click **Start Recording**, your voice will be captured and streamed live.  
**Stop Recording** will send an “end-of-stream,” then transcripts will appear below as they are finalized.
""")
