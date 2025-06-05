import boto3

client = boto3.client('transcribe')

print(client.meta.service_model.operation_model('StartMedicalStreamTranscription').input_shape.members.keys())
