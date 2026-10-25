"""Select the requested macOS camera without falling back to an unrelated device."""
import json
from pathlib import Path
import subprocess


def resolve_camera(name: str, devices=None):
    if devices is None:
        script=Path(__file__).resolve().parents[2]/'scripts/list_cameras.swift'
        result=subprocess.run(['/usr/bin/swift',str(script)],capture_output=True,text=True,timeout=15,check=True)
        devices=json.loads(result.stdout)
    devices=sorted(devices,key=lambda device:device['uid'])
    exact=[(index,device) for index,device in enumerate(devices) if name.casefold() in {device['name'].casefold(),device['uid'].casefold()}]
    matches=exact or [(index,device) for index,device in enumerate(devices) if name.casefold() in device['name'].casefold()]
    if len(matches)!=1:
        raise ValueError(f'Camera {name!r} was not uniquely found. Connect that camera; the MacBook camera will not be used as a fallback.')
    return matches[0][0],matches[0][1]['name']
