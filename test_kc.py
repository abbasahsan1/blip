import os, asyncio, httpx
KEYCLOAK_URL = "http://localhost:8419/keycloak"
async def main():
    async with httpx.AsyncClient() as client:
        t = await client.post(f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
            data={"client_id": "admin-cli", "grant_type": "password", "username": "admin", "password": "admin_master_password"})
        tok = t.json()["access_token"]
        u = await client.get(f"{KEYCLOAK_URL}/admin/realms/blipp/users?username=test789@blipp.com",
            headers={"Authorization": f"Bearer {tok}"})
        print(u.json())
asyncio.run(main())
