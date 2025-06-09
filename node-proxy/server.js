import express from 'express';
import expressWs from 'express-ws';
import {
  TranscribeStreamingClient,
  StartMedicalStreamTranscriptionCommand
} from "@aws-sdk/client-transcribe-streaming";

const { app } = expressWs(express());
const PORT = 3000;

class AudioStream {
  constructor() {
    this.queue = [];
    this.resolve = null;
  }
  sendAudio(chunk) {
    this.queue.push({ AudioEvent: { AudioChunk: chunk } });
    if (this.resolve) {
      this.resolve();
      this.resolve = null;
    }
  }
  end() {
    this.queue.push(null);
    if (this.resolve) {
      this.resolve();
      this.resolve = null;
    }
  }
  async *[Symbol.asyncIterator]() {
    while (true) {
      if (!this.queue.length) {
        await new Promise(r => this.resolve = r);
      }
      const evt = this.queue.shift();
      if (evt === null) break;
      yield evt;
    }
  }
}

const REGION = "us-east-1";
const client = new TranscribeStreamingClient({ region: REGION });

app.ws('/api/stream', (ws, req) => {
  console.log("🔌 Client connected");

  const audioStream = new AudioStream();

  ws.on('message', (msg) => {
    if (Buffer.isBuffer(msg)) {
      if (msg.length === 0) {
        console.log("📴 Received EOS signal from client");
        audioStream.end();
      } else {
        audioStream.sendAudio(msg);
      }
    }
  });

  (async () => {
    try {
      const command = new StartMedicalStreamTranscriptionCommand({
        LanguageCode: "en-US",
        MediaSampleRateHertz: 48000,
        MediaEncoding: "pcm",
        Specialty: "PRIMARYCARE",
        Type: "DICTATION",
        AudioStream: audioStream
      });

      const response = await client.send(command);

      for await (const event of response.TranscriptResultStream) {
        if (event.Transcript?.Results) {
          for (const result of event.Transcript.Results) {
            if (!result.IsPartial && result.Alternatives.length > 0) {
              const transcriptText = result.Alternatives[0].Transcript;
              console.log("📝 Final Transcript:", transcriptText);
            } else if (result.IsPartial) {
              console.log("⏳ Partial Transcript (not logged in full)");
            }
          }
        }
        ws.send(JSON.stringify(event));
      }

      console.log("✅ All transcripts sent; closing WS");
      ws.close();
    } catch (err) {
      console.error("❌ Error in AWS stream:", err);
      ws.send(JSON.stringify({ error: err.message }));
      ws.close();
    }
  })();
});

app.listen(PORT, () => {
  console.log(`🚀 Proxy listening at ws://localhost:${PORT}/api/stream`);
});
