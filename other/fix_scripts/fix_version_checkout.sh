git submodule foreach '
  git fetch origin
  git checkout main || git checkout -b main origin/main
  git pull origin main
'