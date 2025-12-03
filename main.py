import sys
import time

def process_data():
    """
    Placeholder function for your core logic.
    """
    print("  [INFO] Processing data...")
    # Simulate work
    time.sleep(1)
    print("  [INFO] Task complete.")

def main():
    """
    Main entry point of the application.
    """
    print("--- Starting Application ---")
    
    # Example logic execution
    process_data()
    
    print("--- Application Finished ---")

if __name__ == "__main__":
    # This block ensures the code runs only when executed directly,
    # not when imported as a module.
    try:
        main()
    except KeyboardInterrupt:
        # Handles Ctrl+C gracefully
        print("\n[!] Program interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        # Catches unexpected errors to prevent ugly stack traces
        print(f"\n[ERROR] An unexpected error occurred: {e}")
        sys.exit(1)
