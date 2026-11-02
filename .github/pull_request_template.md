## Summary

<!-- What does this change do, in one or two sentences? -->

## Type of change

- [ ] Receiver, router, queue or launcher (the path from the phone to `claude` - describe below)
- [ ] CLI, doctor, config or installer
- [ ] Documentation
- [ ] CI / tooling

## Safety impact

<!-- If this touches the path from the phone to `claude`, say how the task text travels now,
     and confirm it still never passes through a shell. -->

## Verification

- [ ] `./run_tests.sh` passes locally
- [ ] Tested on a real Mac with `nearsay test "…"` (and, if the receiver changed, a real tap)

## Safety rules

- [ ] The phone's key still runs the receiver and nothing else
- [ ] The task text still never reaches a shell
- [ ] The phone still cannot choose the folder, permission mode, model or program
- [ ] No new dependencies; still runs on Python 3.9
