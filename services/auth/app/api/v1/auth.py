import logging
import os
import httpx
from fastapi import APIRouter, status, HTTPException
from app.models.schemas import UserRegisterRequest

logger = logging.getLogger("auth.api")
router = APIRouter(tags=["Auth"])

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://keycloak.blipp.svc.cluster.local:8080")
KEYCLOAK_ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
KEYCLOAK_ADMIN_PASSWORD = os.environ["KEYCLOAK_ADMIN_PASSWORD"]

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserRegisterRequest):
    username = payload.email.split('@')[0]
    
    async with httpx.AsyncClient() as client:
        # 1. Get Admin Token
        token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
        try:
            token_resp = await client.post(
                token_url,
                data={
                    "client_id": "admin-cli",
                    "grant_type": "password",
                    "username": KEYCLOAK_ADMIN_USER,
                    "password": KEYCLOAK_ADMIN_PASSWORD
                }
            )
            token_resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get admin token: {e.response.text}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

        admin_data = token_resp.json()
        access_token = admin_data.get("access_token")

        # 2. Create User in Blipp Realm
        create_url = f"{KEYCLOAK_URL}/admin/realms/blipp/users"
        user_data = {
            "username": payload.email,
            "email": payload.email,
            "enabled": True,
            "emailVerified": True,
            "firstName": payload.display_name or username,
            "lastName": "User",
            "credentials": [{"type": "password", "value": payload.password, "temporary": False}],
            "requiredActions": []
        }
        
        try:
            create_resp = await client.post(
                create_url,
                headers={"Authorization": f"Bearer {access_token}"},
                json=user_data
            )
            create_resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == status.HTTP_409_CONFLICT:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
            logger.error(f"Failed to create user: {e.response.text}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user")

        # Keycloak returns 201 with a Location header for the new user, we can extract the user ID if needed.
        # But we can also just login directly to get the token and user profile via userinfo.
        
        # 3. Login as new user
        login_url = f"{KEYCLOAK_URL}/realms/blipp/protocol/openid-connect/token"
        try:
            login_resp = await client.post(
                login_url,
                data={
                    "client_id": "blipp-app",
                    "grant_type": "password",
                    "username": payload.email,
                    "password": payload.password
                }
            )
            login_resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to login newly created user: {e.response.text}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to login newly created user")

        login_data = login_resp.json()
        import base64
        import json
        user_id = ""
        try:
            payload_part = login_data['access_token'].split('.')[1]
            payload_part += '=' * (-len(payload_part) % 4)
            decoded = base64.urlsafe_b64decode(payload_part)
            jwt_data = json.loads(decoded)
            user_id = jwt_data.get("sub", "")
        except Exception as e:
            logger.error(f"Failed to extract sub from JWT: {e}")

        return {
            "access_token": login_data.get("access_token"),
            "refresh_token": login_data.get("refresh_token"),
            "expires_in": login_data.get("expires_in"),
            "user": {
                "id": user_id,
                "email": payload.email
            }
        }
