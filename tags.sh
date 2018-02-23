#!/bin/sh

cd "$(dirname "$(readlink -f "$0")")"

exec ctags -f .tags --recurse --python-kinds=-i
