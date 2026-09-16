#!/bin/bash
TOKEN="dev-token-00000000-0000-0000-0000-000000000001"
echo "test" > test_audio.mp3
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "http://localhost/v1/uploads" -H "Authorization: Bearer ${TOKEN}" -F "file=@test_audio.mp3" -F "upload_type=audio" -F "title=Verification Clip" -F "description=Testing async pipeline")
echo "$RESPONSE"
UPLOAD_ID=$(echo "$RESPONSE" | grep -o '"upload_id":"[^"]*' | grep -o '[^"]*$')
if [ -z "$UPLOAD_ID" ]; then
    echo "Upload ID not found"
    exit 1
fi
echo "Upload ID: $UPLOAD_ID"
echo "Sleeping for 10 seconds to allow pipeline to process..."
sleep 10
curl -s -X GET "http://localhost/v1/uploads/${UPLOAD_ID}" -H "Authorization: Bearer ${TOKEN}" | jq
