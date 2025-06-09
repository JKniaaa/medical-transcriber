import express from 'express';
import cors from 'cors';
import expressWs from 'express-ws';
import {
  TranscribeStreamingClient,
  StartMedicalStreamTranscriptionCommand
} from "@aws-sdk/client-transcribe-streaming";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";

// Initialize S3 client (region should match your bucket's region)
const s3Client = new S3Client({ region: "ap-southeast-2" });

const { app } = expressWs(express());
const PORT = 3000;

// Enable CORS for your Streamlit app origin
app.use(cors({
  origin: 'http://localhost:8501',  // allow Streamlit frontend
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type']
}));

app.use(express.json());

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

const REGION = "ap-southeast-2";
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


app.post('/api/save', async (req, res) => {
  const { transcript } = req.body;
  if (!transcript) {
    return res.status(400).json({ error: "Transcript missing" });
  }

  // Prepare S3 upload parameters
  const bucketName = "my-medical-transcribe-bucket";  // <-- replace with your actual bucket name
  const objectKey = `stream-transcripts/transcript-${Date.now()}.txt`; // unique filename

  const params = {
    Bucket: bucketName,
    Key: objectKey,
    Body: transcript,
    ContentType: "text/plain"
  };

  try {
    // Upload to S3
    await s3Client.send(new PutObjectCommand(params));

    console.log(`💾 Saved transcript to s3://${bucketName}/${objectKey}`);

    res.status(200).json({ message: "Transcript saved!" });
  } catch (err) {
    console.error("❌ Failed to save transcript to S3:", err);
    res.status(500).json({ error: "Failed to save transcript" });
  }
});


app.listen(PORT, () => {
  console.log(`🚀 Proxy listening at ws://localhost:${PORT}/api/stream`);
});
