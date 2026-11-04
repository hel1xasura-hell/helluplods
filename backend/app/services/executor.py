"""Decide where a task runs so work is never duplicated. Exactly one executor per task.

cloud -> cloud worker.  local -> paired local device (error if none online).
both  -> deterministic split: research/screenshots run in the cloud; recordings run on a local device when one is
online (real desktop capture), otherwise in the cloud. The choice is stored on the task."""

CLOUD, LOCAL = "cloud", "local"
CLOUD_ONLY_KINDS = {"research", "screenshot"}  # device-side research is not built yet, so these always run in the cloud


class NoLocalDevice(Exception):
    pass


def choose_executor(mode: str, kind: str, local_device_online: bool) -> str:
    if mode not in {"cloud", "local", "both"}:
        raise ValueError(f"Unknown execution mode: {mode}")
    if mode == "cloud" or kind in CLOUD_ONLY_KINDS:
        return CLOUD
    if local_device_online:
        return LOCAL
    if mode == "local":
        raise NoLocalDevice("This project runs locally, but no paired device is online.")
    return CLOUD  # mode == "both": fall back to the cloud, still exactly one executor
