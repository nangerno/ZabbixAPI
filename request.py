import requests

# BASE_URL = 'http://10.10.2.55:8000'
BASE_URL = 'http://167.88.165.19:8000'

def send_request(action, data):
    url = f'{BASE_URL}/manage_device'
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        print(f"{action.capitalize()} action: Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"{action.capitalize()} action failed:")
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")
    print("-" * 50)

def test_manage_device():
    # create
    create_data = {
        'action': 'create',
        'device': {
            'name': 'xxxxxxxxxxx',  # you can set as your device name
            'dns': 'qwerty-device-10.example.com',
            'inventory': {
                'type': 'SIP Phone',
                'name': 'Model X',
                'alias': 'SN123456',
                'os': 'xxx',
            },
            'template': 'Template Module ICMP Ping' # Ensure if this template exists
        },
        'group': 'qwerty',
        'map_name': 'qwerty'
    }
    send_request('create', create_data)

    # update
    update_data = {
        'action': 'update',
        'device': {
            'name': 'qwerty',
            'dns': 'qwerty2-device-10-updated.example.com',
            'inventory': {
                'type': 'SIP Phone',
                'name': 'Model Y',
                'alias': 'SN123456',
                'os': 'YYY',
            },
            'template': 'Template Module ICMP Ping'
        },
        'group': 'qwerty',
        'map_name': 'qwerty'
    }
    # send_request('update', update_data)

    # delete
    delete_data = {
        'action': 'delete',
        'device': {
            'name': 'qwerty',
            'template': '',
        },
        
        'group': 'qwerty',
        'map_name': 'qwerty'
    }
    # send_request('delete', delete_data)


if __name__ == '__main__':
    print(f"Connecting to Flask app at: {BASE_URL}")
    print("-" * 50)
    test_manage_device()
    print("Test completed.")