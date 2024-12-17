from flask import Flask, request, jsonify
from pyzabbix import ZabbixAPI, ZabbixAPIException
import threading
import sqlite3
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
load_dotenv()
executor = ThreadPoolExecutor(max_workers=5)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

ZABBIX_URL = os.getenv('ZABBIX_URL')
ZABBIX_USER = os.getenv('ZABBIX_USER')
ZABBIX_PASSWORD = os.getenv('ZABBIX_PASSWORD')

zapi = ZabbixAPI(ZABBIX_URL)
zapi.login(ZABBIX_USER, ZABBIX_PASSWORD)

def test_zabbix_connection():
    try:
        api_version = zapi.api_version()
        print(f"Connected to Zabbix API. Version: {api_version}")
    except ZabbixAPIException as e:
        print(f"Failed to connect to Zabbix API: {e}")

test_zabbix_connection()

def init_db():
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (id INTEGER PRIMARY KEY, name TEXT, dns TEXT, group_name TEXT)''')
    conn.commit()
    conn.close()

init_db()

def update_map(group_name, hosts, map_name):
    try:
        maps = zapi.map.get(filter={'name': map_name})
        if maps:
            map_id = maps[0]['sysmapid']
            print(f"Updating existing map '{map_name}'")
        else:
            map_params = {
                'name': map_name,
                'width': 680,
                'height': 200,
                'label_type': 0,
                'label_location': 0,
                'highlight': 1,
                'expandproblem': 1,
                'markelements': 1,
                'show_unack': 0,
                'severity_min': 0,
                'show_suppressed': 0,
                'grid_size': 100,
                'grid_show': 1,
                'grid_align': 0,
                'label_format': 0,
                'label_type_host': 2,
                'label_type_hostgroup': 2,
                'label_type_trigger': 2,
                'label_type_map': 2,
                'label_type_image': 2,
                'expand_macros': 1
            }
            map_create = zapi.map.create(**map_params)
            map_id = map_create['sysmapids'][0]
            print(f"Created new map '{map_name}'")

            dummy_element = {
                'elementtype': 4,
                'elementid': '0',
                'label': 'Dummy Element',
                'x': 0,
                'y': 0,
                'elementsubtype': 0,
                'areatype': 0,
                'width': 100,
                'height': 100,
                'iconid_off': zapi.image.get(filter={'name': "Dummy"})[0]['imageid'],
            }
            zapi.map.update(sysmapid=map_id, selements=[dummy_element])

        elements_to_add = []
        for i, host in enumerate(hosts):
            icon_image = zapi.image.get(filter={'name': "Phone_(24)"})
            iconid_off = icon_image[0]['imageid'] if icon_image else None
            elements_to_add.append({
                'elementtype': 0,
                'elementid': host['hostid'],
                'label': '{HOST.NAME} {HOST.CONN}',
                'label_location': -1,
                'x': (i * 100) % 680,
                'y': (i // 6) * 50,
                'elementsubtype': 0,
                'areatype': 0,
                'width': 200,
                'height': 200,
                'viewtype': 0,
                'use_iconmap': 0,
                'iconid_off': iconid_off,
                'urls': [{'name': host['host'], 'url': f"https://{host['host']}"}],
                'elements': [{'hostid': host['hostid']}]
            })

        if elements_to_add:
            zapi.map.update(sysmapid=map_id, selements=elements_to_add)
            print(f"Added {len(elements_to_add)} new elements to the map")

    except ZabbixAPIException as e:
        print(f"Error updating map: {e}")

def get_or_create_group(group_name):
    try:
        group = zapi.hostgroup.get(filter={'name': group_name})
        if group:
            group_id = group[0]['groupid']
            print(f"Group '{group_name}' found with ID: {group_id}")
        else:
            print(f"Group '{group_name}' not found, creating...")
            result = zapi.hostgroup.create(name=group_name)
            group_id = result['groupids'][0]
            print(f"Group '{group_name}' created with ID: {group_id}")
        return group_id
    except ZabbixAPIException as e:
        print(f"Error in get_or_create_group: {e}")
        return None

@app.route('/manage_device', methods=['POST'])
@limiter.limit("10 per minute")
def manage_device():
    try:
        data = request.json or request.form.to_dict()
        action = data['action']
        device = data['device']
        group_name = data['group']
        map_name = data['map_name']        
        conn = sqlite3.connect('devices.db')
        c = conn.cursor()

        group_id = get_or_create_group(group_name)
        if not group_id:
            return jsonify({'status': 'error', 'message': 'Failed to get or create group'}), 400

        if action in ['create', 'update']:
            host_params = {
                'host': device['name'],
                'interfaces': [{
                    'type': 1,
                    'main': 1,
                    'useip': 0,
                    'ip': '',
                    'dns': device['dns'],
                    'port': '10050'
                }],
                'groups': [{'groupid': group_id}],
                'inventory_mode': 1,
                'inventory': device.get('inventory', {}),
                'status': 0
            }
            if device['template']:
                template = zapi.template.get(filter={'name': device['template']})
                if action == 'create':
                    host_params['templates'] = [{'templateid': template[0]['templateid']}]
                elif action == 'update':
                    host_params['templates_clear'] = [{'templateid': template[0]['templateid']}]

            if action == 'create':
                existing_hosts = zapi.host.get(filter={'host': device['name']})
                if existing_hosts:
                    return jsonify({'status': 'error', 'message': f'Host "{device["name"]}" already exists'}), 400
                result = zapi.host.create(**host_params)
                host_id = result['hostids'][0]
                c.execute("INSERT INTO devices (name, dns, group_name) VALUES (?, ?, ?)",
                        (device['name'], device['dns'], group_name))
                print("------Create-----")
                print(f"Created host '{device['name']}' with ID: {host_id}")
            else:
                hosts = zapi.host.get(filter={'host': device['name']})
                if hosts:
                    host_id = hosts[0]['hostid']
                    zapi.host.update(hostid=host_id, **host_params)
                    c.execute("UPDATE devices SET dns = ?, group_name = ? WHERE name = ?",
                              (device['dns'], group_name, device['name']))
                    print("------Update-----")
                    print(f"Updated host '{device['name']}' with ID: {host_id}")
                else:
                    conn.close()
                    return jsonify({'status': 'error', 'message': f'Host "{device["name"]}" not found for update'}), 404
            conn.commit()

        if action == 'delete':
            hosts = zapi.host.get(filter={'host': device['name']})
            for host in hosts:
                print(f"Founded Host ID: {host['hostid']}, Name: {host['name']}")
            if hosts:
                print("------Delete-----")
                host_id = hosts[0]['hostid']
                try:
                    zapi.host.delete(host_id)
                    c.execute("DELETE FROM devices WHERE name = ?", (device['name'],))
                    conn.commit()
                    print(f"Deleted host '{device['name']}' with ID: {host_id}")
                except ZabbixAPIException as e:
                    print(f"Error deleting host: {e}")
                    return jsonify({'status': 'error', 'message': f"Failed to delete host '{device['name']}': {str(e)}"}), 500
            else:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Host not found for deletion'}), 404

        conn.close()

        threading.Thread(target=update_map, args=(group_name, zapi.host.get(groupids=[group_id]), map_name)).start()

        return jsonify({'status': 'success', 'message': f'Device {action} completed successfully'})

    except ZabbixAPIException as e:
        print(f"Zabbix API Exception: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    except KeyError as e:
        print(f"Missing key in request: {e}")
        return jsonify({'status': 'error', 'message': f'Missing key: {e}'}), 400
    except Exception as e:
        print(f"Unexpected error: {e}")
        return jsonify({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, threaded=True, port=8000)