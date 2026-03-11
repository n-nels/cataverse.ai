import sys

import requests


class KasaControl:
    def __init__(self, username, password, device_id):
        # Define endpoints for failover
        self.endpoints = ["https://use1-wap.tplinkcloud.com", "https://wap.tplinkcloud.com", ]
        self.username = username
        self.password = password
        self.device_id = device_id
        self.token = None
        self.url = None

    def login(self) -> str:
        """Logs into the Kasa cloud and retrieves the token."""
        print("Logging in...")
        payload = {
            "method": "login",
            "params": {
                "appType": "Kasa_iOS",  # Change to Kasa_Android if needed
                "cloudUserName": self.username,
                "cloudPassword": self.password,
                "terminalUUID": "test-uuid",
            }
        }

        # Try each endpoint in the failover list
        for endpoint in self.endpoints:
            # print(f"Trying endpoint: {endpoint}")
            try:
                response = requests.post(endpoint, json=payload, timeout=10)
                response_json = response.json()
                # print(f"Login Response: {response_json}")

                if response_json.get("error_code") == 0:
                    self.token = response_json["result"]["token"]
                    # print(f"Login successful with endpoint: {endpoint}")
                    self.url = endpoint
                    return self.token

                else:
                    # Login failed with this endpoint
                    error_msg = response_json.get("msg", "Unknown error")
                    print(f"Login failed: {error_msg}")

            except Exception as e:
                print(f"Login error with endpoint {endpoint}: {e}")

        # If no endpoints worked
        print("All endpoints failed. Unable to log in.")
        return None

    def control(self, state: bool) -> dict:
        """
        Controls the Kasa smart plug.
        :param state: True to turn on, False to turn off.
        :return: Response from the Kasa API.
        """
        if not self.token:
            if not self.login():
                print("Unable to log in. Cannot control the device.")
                return {}

        print(f"Turning plug {'ON' if state else 'OFF'}...")
        payload = {
            "method": "passthrough",
            "params": {
                "deviceId": self.device_id,
                "requestData": {
                    "system": {"set_relay_state": {"state": 1 if state else 0}},
                },
            },
        }

        try:
            device_url = f"{self.url}?token={self.token}"
            response = requests.post(device_url, json=payload, timeout=10)
            response_json = response.json()

            # Debugging: Print the full response
            # print(f"Control Response: {response_json}")

            return response_json

        except Exception as e:
            print(f"Control error: {e}")
            return {}

def main(device_name, state):
    username = "nelsonnicholasc@gmail.com"  # Replace with your username
    password = "automate1"          # Replace with your password

    # Replace with your actual device ID
    kasa = KasaControl(username, password, device_name)
    result = kasa.control(state)

    if result.get('error_code') == 0:
        status = "ON" if state else "OFF"
        print(f"Device successfully turned {status}.")
    else:
        print("Failed to control the device.")

def get_devices_id() -> None:
    """
    Fetches the device IDs from the Kasa cloud API.
    """
    username = "nelsonnicholasc@gmail.com"
    password = "automate1"  # Your password here

    print("Getting token...")
    url = "https://wap.tplinkcloud.com"
    login_payload = {
        "method": "login",
        "params": {
            "appType": "Kasa_iOS", # Change to Kasa_Android or Kasa_iOS if needed
            "cloudUserName": username,
            "cloudPassword": password,
            "terminalUUID": "test-uuid",
        }
    }

    try:
        print("Logging in...")
        response = requests.post(url, json=login_payload, timeout=10)
        print(f"Response: {response.json()}")
        token = response.json()['result']['token']
        print("Login successful!")

        print("\nFetching devices...")
        device_payload = {
            "method": "getDeviceList"
        }
        device_url = f"{url}?token={token}"
        
        device_response = requests.post(device_url, json=device_payload, timeout=10)
        devices = device_response.json()
        
        print("\nYour devices:")
        for device in devices['result']['deviceList']:
            print(f"\nDevice Name: {device.get('alias', 'Unknown')}")
            print(f"Device ID: {device.get('deviceId', 'Unknown')}")
            print(f"Model: {device.get('deviceModel', 'Unknown')}")
            print(f"Status: {'Online' if device.get('status') == 1 else 'Offline'}")
            
    except Exception as e:
        print(f"Error: {e}")

def test_login_variations():
    username = "nelsonnicholasc@gmail.com"
    password = "automate1"
    
    # Test different parameter combinations
    variations = [
        {
            "method": "login",
            "params": {
                "appType": "Kasa_Android",
                "cloudUserName": username,
                "cloudPassword": password,
                "terminalUUID": "test-uuid"
            }
        },
        {
            "method": "login", 
            "params": {
                "appType": "Kasa_iOS",
                "cloudUserName": username,
                "cloudPassword": password,
                "terminalUUID": "test-uuid",
                "refreshTokenNeeded": True
            }
        },
        {
            "method": "login",
            "params": {
                "appType": "Kasa_Android",
                "cloudUserName": username,
                "cloudPassword": password,
                "terminalUUID": "test-uuid",
                "appVer": "2.35.0"
            }
        }
    ]
    
    urls = [
        "https://wap.tplinkcloud.com",
        "https://use1-wap.tplinkcloud.com"
    ]
    
    for i, payload in enumerate(variations):
        for j, url in enumerate(urls):
            print(f"\nTrying variation {i+1} with URL {j+1}...")
            try:
                response = requests.post(url, json=payload, timeout=10)
                result = response.json()
                print(f"Result: {result}")
                if result.get('error_code') == 0:
                    print("SUCCESS!")
                    return result['result']['token']
            except Exception as e:
                print(f"Error: {e}")
    
    return None


if __name__ == '__main__':
    chiller = "80068F39DE57BDF8D6EA6F2AB145251E223AF901"
    variac = "80068C02EA20EFE6A7149420FAA20DB5223A54AA"
    variac_2 = "8006CF042D478C8A62FE5B07A53B29B8223A2135"

    if len(sys.argv) > 1:
        state = True if sys.argv[2] == "True" else False
        main(sys.argv[1], state)
    else:
        print('Something bad happened')

    # get_devices_id()
    # test_login_variations()
    # main(chiller, True)  # Turn on chiller


