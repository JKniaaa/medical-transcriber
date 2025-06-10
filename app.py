import streamlit as st
import boto3
import time
import uuid
import os
from tempfile import NamedTemporaryFile
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# AWS configuration
region = os.getenv('AWS_REGION')
s3_bucket = os.getenv('S3_BUCKET')

# Initialize AWS clients
s3 = boto3.client('s3', region_name=region)
transcribe = boto3.client('transcribe', region_name=region)

st.set_page_config(page_title="Live Medical Transcription (Batch)", layout="wide")
st.title("AWS Medical Transcribe Voice-to-Text")

audio_file = st.audio_input("Record a voice message")

if audio_file:
    st.audio(audio_file)

    if st.button("Upload & Start Transcription"):
        # Save audio to temp file
        with NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_file.read())
            audio_path = tmp_file.name

        # Upload to S3
        try:
            file_key = f"streamlit-audio/{uuid.uuid4()}.wav"
            s3.upload_file(audio_path, s3_bucket, file_key)
            s3_uri = f"s3://{s3_bucket}/{file_key}"
            st.write("Uploaded to S3:", s3_uri)
        except Exception as e:
            st.error(f"Failed to upload audio to S3: {e}")
            os.remove(audio_path)
            st.stop()

        # Start Transcription Job
        job_name = f"transcription-job-{uuid.uuid4()}"
        transcribe.start_medical_transcription_job(
            MedicalTranscriptionJobName=job_name,
            LanguageCode='en-US',
            MediaFormat='wav',
            Media={'MediaFileUri': s3_uri},
            OutputBucketName=s3_bucket,
            Specialty='PRIMARYCARE',
            Type='DICTATION'
        )

        st.write("Transcription job started...")

        # Poll for completion
        while True:
            status = transcribe.get_medical_transcription_job(MedicalTranscriptionJobName=job_name)
            job_status = status['MedicalTranscriptionJob']['TranscriptionJobStatus']
            if job_status in ['COMPLETED', 'FAILED']:
                break
            st.write("Waiting for job to complete...")
            time.sleep(7)

        if job_status == 'COMPLETED':
            output_uri = status['MedicalTranscriptionJob']['Transcript']['TranscriptFileUri']
            parsed = urlparse(output_uri)
            path_parts = parsed.path.lstrip('/').split('/', 1)
            if path_parts[0] == s3_bucket:
                output_key = path_parts[1] if len(path_parts) > 1 else ''
            else:
                output_key = parsed.path.lstrip('/')
            bucket_name = s3_bucket

            max_retries = 10
            delay = 3
            transcript_text = ""
            for attempt in range(max_retries):
                try:
                    presigned_url = s3.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': bucket_name, 'Key': output_key},
                        ExpiresIn=3600
                    )
                    response = requests.get(presigned_url)
                    response.raise_for_status()
                    if response.text.strip():
                        transcript_json = response.json()
                        transcript_text = transcript_json['results']['transcripts'][0]['transcript']
                        st.session_state["transcript_text"] = transcript_text

                        # Save original transcription as plain text file in S3
                        original_txt_key = f"transcripts/{job_name}.txt"
                        try:
                            s3.put_object(
                                Bucket=s3_bucket,
                                Key=original_txt_key,
                                Body=transcript_text.encode('utf-8'),
                                ContentType='text/plain'
                            )
                            st.success(f"Original transcript saved as .txt to s3://{s3_bucket}/{original_txt_key}")
                        except Exception as e:
                            st.error(f"Failed to save original transcript as .txt: {e}")
                        break
                    else:
                        st.write(f"Transcript empty, retrying ({attempt + 1}/{max_retries})...")
                except requests.exceptions.RequestException as e:
                    st.write(f"Error fetching transcript: {e} (retry {attempt + 1}/{max_retries})")
                except Exception as e:
                    st.write(f"Error parsing transcript JSON: {e} (retry {attempt + 1}/{max_retries})")

                time.sleep(delay)
                delay *= 1.5
            else:
                st.error("Transcript file could not be retrieved or parsed after multiple attempts.")

        else:
            failure_reason = status['MedicalTranscriptionJob'].get('FailureReason', 'No reason provided')
            st.error(f"Transcription job failed. Reason: {failure_reason}")

        # Cleanup
        os.remove(audio_path)

# ---- Editable Transcript Section (outside the upload/transcribe button block) ----

if "transcript_text" in st.session_state:
    st.subheader("Transcription Result - Editable")
    edited_text = st.text_area("Edit the transcript here:", st.session_state["transcript_text"], height=300)

    if st.button("Save Edited Transcript to S3"):
        edited_key = f"edited-transcripts/edited-{uuid.uuid4()}.txt"
        try:
            s3.put_object(
                Bucket=s3_bucket,
                Key=edited_key,
                Body=edited_text.encode('utf-8'),
                ContentType='text/plain'
            )
            st.success(f"Edited transcript saved to s3://{s3_bucket}/{edited_key}")
        except Exception as e:
            st.error(f"Failed to save edited transcript: {e}")

    st.write("You can select and copy the text above as needed.")
