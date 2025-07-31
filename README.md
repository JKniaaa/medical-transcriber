# 🩺 Medical Voice Transcriber (AWS Transcribe Medical)

This project supports **two modes** of voice transcription using **AWS Transcribe Medical**:

- **Batch mode**: Record first, then transcribe.
- **Streaming mode**: Live transcription as you speak.

---

## 🛠 Step 1 – Create AWS S3 Bucket

Before anything else, log in to your [AWS Console](https://console.aws.amazon.com/) and:

1. Create a new **S3 bucket** (e.g. `medical-transcriptions-2025`).
2. Create an **IAM user** with the following permissions:
   - `s3:PutObject`, `s3:GetObject`
   - `transcribe:StartMedicalTranscriptionJob`
   - `transcribe:GetMedicalTranscriptionJob`
3. Copy the **AWS Access Key ID** and **Secret Access Key**.

**Sample Bucket Policy** (Update with your actual bucket name and account ID):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowTranscribePutObject",
      "Effect": "Allow",
      "Principal": {
        "Service": "transcribe.amazonaws.com"
      },
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::medical-transcriptions-2025/*"
    },
    {
      "Sid": "AllowUserPutAndGetObjects",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<your-account-id>:root"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::medical-transcriptions-2025/*"
    }
  ]
}
```

---

## 🧪 Step 2 - Create a Python Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Linux/Mac
venv\Scripts\activate     # On Windows
```

---

## 📦 Step 3 - Install Python Dependencies

Clone this repo and install dependencies:

```bash
pip install -r requirements.txt
```

If using `invoke` for command shortcuts, install:

```bash
pip install invoke
```

---

## 🌐 Step 4 – Configure .env

At the root of your project, create a `.env` file with the following contents:

```env
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=your_aws_region

S3_BUCKET=your_s3_bucket_name

API_BASE_URL=http://localhost:3000
WS_STREAM_ENDPOINT=ws://localhost:3000/api/stream
PORT=3000
```

---

## 🚀 Step 5 – Choose a Transcription Mode

### 🎙️ Option 1: Batch Transcription

This mode records audio first, then transcribes after uploading to AWS.

**To run:**

```bash
streamlit run batch.py
```

Or if using invoke:

```bash
invoke batch
```

### 🔴 Option 2: Streaming Transcription

This mode transcribes **live** as the user speaks.

**Terminal 1: Start the WebSocket Proxy**

If running for the first time:

```bash
cd node-proxy
npm install
```

then to run:

```bash
cd node-proxy
node server.js
```

or if using invoke:

```bash
invoke back
```

**Terminal 2: Start the Streamlit frontend**

```bash
streamlit run stream.py
```

or if using invoke:

```bash
invoke stream
```

---

## 📁 Project Structure

```bash
.
├── batch.py            # Batch mode UI
├── stream.py           # Streaming mode UI
├── node-proxy/
│   └── server.js       # WebSocket proxy backend
├── tasks.py            # Invoke commands shortcuts
├── .env                # Your credentials and settings
├── requirements.txt
└── README.md
```

---

## 🙏 Acknowledgements & References
- 🧠 Powered by [AWS Transcribe Medical](https://docs.aws.amazon.com/transcribe/latest/dg/transcribe-medical.html)
- 🧰 Streamlit for UI
- 🎤 WebAudio API for client-side recording
- 🔁 Express.js WebSocket proxy for streaming audio to AWS
- 📄 Transcript storage via [Amazon S3](https://aws.amazon.com/s3/)
- ⚙️ invoke CLI for task automation

---

## ❗ Troubleshooting
- **[WebSocket error]** → Make sure node server.js is running.
- **No transcript appears?** → Double-check .env values and AWS permissions.
- **Microphone not detected?** → Use a Chromium-based browser with mic access granted.

---

## 👤 Author

[Goh Jun Keat](https://github.com/JKniaaa) @ 2025









