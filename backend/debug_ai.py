
import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

print("Attempting to import ai_message_drafter...")
try:
    from ai_message_drafter import get_drafter, AIMessageDrafter
    print("Import successful.")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

print("Attempting to call get_drafter()...")
try:
    drafter = get_drafter()
    print(f"get_drafter() returned: {drafter}")
except NameError as e:
    print(f"Caught NameError: {e}")
except Exception as e:
    print(f"Caught Exception: {e}")

print("Attempting to instantiate AIMessageDrafter directly...")
try:
    d = AIMessageDrafter()
    print(f"Direct instantiation successful: {d}")
except Exception as e:
    print(f"Direct instantiation failed: {e}")
