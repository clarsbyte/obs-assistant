import obsws_python as obs
from obsws_python.error import OBSSDKError


def main():
    HOST = "localhost"
    PORT = 4455
    PASSWORD = "3K9hIU30ulS933YK"

    try:
        print(f"Connecting to OBS at {HOST}:{PORT}...")
        cl = obs.ReqClient(host=HOST, port=PORT, password=PASSWORD, timeout=5)
        print("Connected!\n")
    except OBSSDKError as e:
        print(f"\n✖ Could not connect to OBS: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure OBS Studio is open")
        print("  2. Go to Tools → WebSocket Server Settings")
        print("  3. Check 'Enable WebSocket server' is ON")
        print(f"  4. Verify the port is {PORT}")
        print("  5. Verify the password matches (or disable auth)")
        return
    except ConnectionRefusedError:
        print(f"\n✖ Connection refused at {HOST}:{PORT}")
        print("   OBS is probably not running or the port is wrong.")
        return

    # Get OBS version info
    version = cl.get_version()
    print(f"OBS Version: {version.obs_version}")
    print(f"WebSocket Version: {version.obs_web_socket_version}")

    # Get current scene
    scene = cl.get_current_program_scene()
    print(f"Current Scene: {scene.scene_name}")

    # List all sources in the current scene
    items = cl.get_scene_item_list(scene.scene_name)
    print(f"\nSources in '{scene.scene_name}':")
    for item in items.scene_items:
        name = item["sourceName"]
        item_id = item["sceneItemId"]
        enabled = item["sceneItemEnabled"]
        status = "visible" if enabled else "hidden"
        print(f"  [{item_id}] {name} ({status})")

    source_name = input("\nEnter source name to hide (or press Enter to skip): ").strip()
    if source_name:
        hide_source(cl, scene.scene_name, source_name)


def hide_source(cl, scene_name, source_name):
    """Hide a source in the given scene by setting its visibility to False."""
    item_id = cl.get_scene_item_id(scene_name, source_name)
    cl.set_scene_item_enabled(scene_name, item_id.scene_item_id, False)
    print(f"✔ '{source_name}' is now hidden in '{scene_name}'")


def show_source(cl, scene_name, source_name):
    """Show a source in the given scene by setting its visibility to True."""
    item_id = cl.get_scene_item_id(scene_name, source_name)
    cl.set_scene_item_enabled(scene_name, item_id.scene_item_id, True)
    print(f"✔ '{source_name}' is now visible in '{scene_name}'")


if __name__ == "__main__":
    main()
