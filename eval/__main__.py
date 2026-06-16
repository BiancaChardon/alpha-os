from eval.runner import run_eval

if __name__ == "__main__":
    import json

    print(json.dumps(run_eval(), indent=2))
