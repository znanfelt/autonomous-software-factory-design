# Minimal entry point for the modular pipeline
if __name__ == "__main__":
    from main_pipeline.demo import run_demo
    run_demo(cleanup_artifacts=True)
