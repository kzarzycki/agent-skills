import sys

# The engineering loop's script tests load modules from a shipped skill folder;
# a bytecode cache written there would ship with the package.
sys.dont_write_bytecode = True
