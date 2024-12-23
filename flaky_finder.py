import sys
import argparse
import hashlib
import importlib
from typing import NamedTuple

parser = argparse.ArgumentParser(description="Find a first draw call which, when called several times with the same "
                                             "input, gives a different output. "
                                             "Main RenderDoc library (renderdoc.dll or librenderdoc.so) should be in "
                                             "the system library paths.")
parser.add_argument('--rdc', type=str, required=True)
parser.add_argument('--host', type=str, required=False)
parser.add_argument('--python-module', type=str, required=False)

args = parser.parse_args()

if args.python_module is None:
    renderdoc_import = importlib.util.find_spec("renderdoc")
    if renderdoc_import is None:
        raise RuntimeError(
            "No renderdoc python module is found! Use '--python-module' to specify a path to the module.")
else:
    sys.path.append(args.python_module)

# noinspection PyUnresolvedReferences
import renderdoc as rd


class SubresourceDesc(NamedTuple):
    first_mip: int
    first_slice: int


class ResourceKey(NamedTuple):
    rId: rd.ResourceId
    subresource: SubresourceDesc


def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=100, fill='█', print_end="\r"):
    """
    Call in a loop to create terminal progress bar
    https://stackoverflow.com/a/34325723
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        print_end   - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end=print_end)

    # Printing new line is on the caller


def finish_progress_bar():
    print()


def get_output_hashes_of_eid(controller, event_id):
    controller.SetFrameEvent(event_id, True)

    resource_hashes = dict()

    pipeline_state = controller.GetPipelineState()

    color_targets = pipeline_state.GetOutputTargets()
    depth_targets = [pipeline_state.GetDepthTarget()]

    for bound_resource in (color_targets + depth_targets):
        if bound_resource.resource == rd.ResourceId.Null():
            continue

        # TODO: Should we check all slices and mips starting from firstMip and firstSlice?

        subresource = rd.Subresource(bound_resource.firstMip, bound_resource.firstSlice, 0)
        data = controller.GetTextureData(bound_resource.resource, subresource)

        sha1 = hashlib.sha1()
        sha1.update(data)

        subresource_desc = SubresourceDesc(bound_resource.firstMip, bound_resource.firstSlice)
        resource_hashes[ResourceKey(bound_resource.resource, subresource_desc)] = sha1.hexdigest()

    for stage in range(rd.ShaderStage.Count):
        rw_resources = pipeline_state.GetReadWriteResources(stage)
        for rw_descriptor in rw_resources:
            if rw_descriptor.descriptor.resource == rd.ResourceId.Null():
                continue

            data = controller.GetBufferData(rw_descriptor.descriptor.resource, 0, 0)

            sha1 = hashlib.sha1()
            sha1.update(data)

            subresource_desc = SubresourceDesc(0, 0)
            resource_hashes[ResourceKey(rw_descriptor.descriptor.resource, subresource_desc)] = sha1.hexdigest()

    return resource_hashes


def check_for_discrepancy(controller):
    action = controller.GetRootActions()[0]
    while len(action.children) > 0:
        action = action.children[0]

    first_action = action

    total_draw_calls = 0
    while action is not None:
        if action.flags & rd.ActionFlags.Drawcall or action.flags & rd.ActionFlags.Dispatch:
            total_draw_calls += 1
        action = action.next

    action = first_action
    draw_idx = 0
    while action is not None:
        if not (action.flags & rd.ActionFlags.Drawcall or action.flags & rd.ActionFlags.Dispatch):
            action = action.next
            continue

        resource_hashes_a = get_output_hashes_of_eid(controller, action.eventId)
        resource_hashes_b = get_output_hashes_of_eid(controller, action.eventId)

        for key in resource_hashes_a:
            if resource_hashes_a[key] != resource_hashes_b[key]:
                finish_progress_bar()
                print(f"Found discrepancy in EID {action.eventId}, resource {key.rId}")
                return

        draw_idx += 1
        print_progress_bar(draw_idx, total_draw_calls, prefix="Draw Calls:",
                           suffix=f"Checked ({action.GetName(controller.GetStructuredFile())})")
        action = action.next

    finish_progress_bar()
    print(f"No discrepancies found!")


def get_remote_controller(host: str, rdc_path: str):
    status, remote = rd.CreateRemoteServerConnection(host)

    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(f"Couldn't connect to remote server, got error {str(status)}")

    remote_rdc_path = remote.CopyCaptureToRemote(rdc_path,
                                                 lambda progress: print_progress_bar(int(progress * 100), 100,
                                                                                     "Transferring capture:"))
    finish_progress_bar()

    status, controller = remote.OpenCapture(rd.RemoteServer.NoPreference, remote_rdc_path, rd.ReplayOptions(),
                                            lambda progress: print_progress_bar(int(progress * 100), 100,
                                                                                "Opening capture:"))

    if status != rd.ResultCode.Succeeded:
        raise RuntimeError(f"Couldn't open {remote_rdc_path} on remote, got error {str(status)}")

    return controller


def get_local_controller(rdc_path: str):
    cap = rd.OpenCaptureFile()
    status = cap.OpenFile(rdc_path, '', None)

    if status != rd.ResultCode.Succeeded:
        raise RuntimeError("Couldn't open file: " + str(status))

    if not cap.LocalReplaySupport():
        raise RuntimeError("Capture cannot be replayed")

    status, controller = cap.OpenCapture(rd.ReplayOptions(),
                                         lambda progress: print_progress_bar(int(progress * 100), 100,
                                                                             "Opening capture:"))

    if status != rd.ResultCode.Succeeded:
        raise RuntimeError("Couldn't initialise replay: " + str(status))

    return controller


def get_controller(host: str, rdc_path: str):
    if host is not None:
        return get_remote_controller(host, rdc_path)
    else:
        return get_local_controller(rdc_path)


rd.InitialiseReplay(rd.GlobalEnvironment(), [])

controller = get_controller(args.host, args.rdc)
check_for_discrepancy(controller)
controller.Shutdown()

rd.ShutdownReplay()
