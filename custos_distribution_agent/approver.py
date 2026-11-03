"""Human approval — explicit owner consent required after a CUSTOS ALLOW."""


def human_approval(action) -> bool:
    print(f"\n[APPROVAL REQUIRED] {action.kind.value}")
    print(f"  video:  {action.video_id or '(channel-wide)'}")
    print(f"  action: {action.action_id}")
    for k, v in action.payload.items():
        print(f"  {k}: {v}")
    try:
        answer = input("\nApprove this action? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer == "y"
