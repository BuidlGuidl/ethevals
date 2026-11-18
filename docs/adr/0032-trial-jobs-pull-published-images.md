---
status: accepted
---

# Trial jobs pull the published shared images

Every trial and regrade job built both shared images before it started, 56 to 118 seconds per job.
`release.yml` already publishes the same images to GHCR under tags made from their build inputs.
The images' Python packages are not pinned, so a job's own build could hold newer packages than the published image with the same tag.
Two trials under one tag could therefore run with different packages, depending on the day each job built its image.

## The decision

Trial and regrade jobs pull the published image for each shared image their tasks name.
A job builds an image only when its tag is not published yet, which happens when a trial job starts before `release.yml` has pushed a new tag.
A job prepares no image its tasks do not name.

One tag now means one image for every trial that pulls it, the same image people get when they run a task themselves.
Pull-request and fork jobs keep building locally.

Keep image tags, task hashes, scoring, and retry rules unchanged. No saved trial reruns.
Pinning the images' Python packages would change both tags and every task's environment hash, so it stays a separate decision.
