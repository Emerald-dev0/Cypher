# Shared CI diagnostics helper. Source it; do not execute it.
#
#   source "$GITHUB_WORKSPACE/.github/scripts/annotate.sh"
#
# WHY THIS EXISTS
# GitHub Actions job *logs* are served from results-receiver.actions.githubusercontent.com,
# a different host from api.github.com, and are unreachable from some
# environments. Step summaries ($GITHUB_STEP_SUMMARY) turn out not to be readable
# through the API either. Workflow-command **annotations** are the only diagnostic
# channel that reliably survives, via:
#
#   gh api repos/OWNER/REPO/actions/jobs/JOB_ID \
#     --jq '.steps[] | select(.conclusion=="failure") | .name'
#   gh api repos/OWNER/REPO/check-runs/JOB_ID/annotations --jq '.[].message'
#
# So a step that fails without annotating is a step that cannot be debugged.
# See docs/AUDIT.md S-18f and S-18g, and AGENTS.md §6.
#
# TWO RULES THAT ARE NOT OBVIOUS
#
# 1. Any step sourcing this file MUST begin with `set +e`. The runner invokes the
#    default shell as `bash -e {0}` (on Windows, `bash --noprofile --norc -e -o
#    pipefail {0}`), so errexit is already on. A step that adds `pipefail` to
#    capture ${PIPESTATUS[0]} then aborts at the failing pipeline, before any
#    diagnostic runs. That is S-18f, and it defeated three successive versions of
#    the analyzer step.
#
# 2. GitHub silently DROPS annotations past a small undocumented limit — one job
#    recorded 12 in total while 10 findings existed and only 9 arrived. Always emit
#    a COUNT first, as its own small annotation, so the reader knows how much of
#    the sample is missing. That is S-18g. A count you can trust beats a list you
#    cannot.

# annotate <file> [max] — emit each non-empty line of <file> as its own annotation.
#
# No pattern matching happens here on purpose. An emitter that only fires on output
# shaped the way its author expected is how the analyzer findings went unreported
# twice (S-18g): a `grep` for one bullet character silently matched nothing.
annotate() {
  local f="$1" max="${2:-50}" n=0
  if [ ! -f "$f" ]; then
    echo "::error::annotate: no such file '$f' — the step produced no output to report."
    return 0
  fi
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    n=$((n + 1))
    [ "$n" -le "$max" ] || continue
    # GitHub treats %, CR and LF as special in workflow commands.
    line=${line//%/%25}
    line=${line//$'\r'/%0D}
    line=${line//$'\n'/%0A}
    echo "::error::${line}"
  done < "$f"
  if [ "$n" -gt "$max" ]; then
    echo "::error::$((n - max)) further finding(s) suppressed; see the job log."
  fi
  echo "annotate: emitted $n line(s) from $f (cap $max)."
}

# count_first <label> <total> <detail> — emit the authoritative count BEFORE the
# sample, because it is the annotation most likely to survive the drop limit.
count_first() {
  echo "::error::$1: $2. $3"
}
