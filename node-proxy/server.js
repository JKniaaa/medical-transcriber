import express from 'express';
import cors from 'cors';
import expressWs from 'express-ws';
import dotenv from 'dotenv';
import {
  TranscribeStreamingClient,
  StartMedicalStreamTranscriptionCommand
} from "@aws-sdk/client-transcribe-streaming";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";

// Load environment variables
dotenv.config();

// Environment constants
const REGION = process.env.AWS_REGION;
const BUCKET = process.env.S3_BUCKET;
const PORT = process.env.PORT || 3000;

// AWS clients
const transcribeClient = new TranscribeStreamingClient({ region: REGION });
const s3Client = new S3Client({ region: REGION });

const { app } = expressWs(express());

// CORS for Streamlit frontend
app.use(cors({
  origin: 'http://localhost:8501',
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type']
}));

app.use(express.json());

// Audio stream utility
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

// WebSocket transcription route
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

      const response = await transcribeClient.send(command);

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

// Save transcript route
app.post('/api/save', async (req, res) => {
  const { transcript } = req.body;
  if (!transcript) {
    return res.status(400).json({ error: "Transcript missing" });
  }

  const objectKey = `stream-transcripts/transcript-${Date.now()}.txt`;

  const params = {
    Bucket: BUCKET,
    Key: objectKey,
    Body: transcript,
    ContentType: "text/plain"
  };

  try {
    await s3Client.send(new PutObjectCommand(params));
    console.log(`💾 Saved transcript to s3://${BUCKET}/${objectKey}`);
    res.status(200).json({ message: "Transcript saved!" });
  } catch (err) {
    console.error("❌ Failed to save transcript to S3:", err);
    res.status(500).json({ error: "Failed to save transcript" });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Proxy listening at ws://localhost:${PORT}/api/stream`);
});
