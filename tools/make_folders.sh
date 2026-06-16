#!/bin/bash
# Create the working folders the workflow expects, in the current directory.
# Run this in whatever folder you want to process captions in.
set -e
for d in Raw_Captions Edited_Captions Archived_Captions VTT_Files HTML_Transcripts; do
  mkdir -p "$d" && echo "  $d/"
done
echo "Folders ready. Put caption files in Raw_Captions and start Caption Cleanup."
