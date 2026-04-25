require 'mkmf'
$CFLAGS='-I../../include'
$CXXFLAGS='-I../../include'
$LDFLAGS="-lstdc++"

create_makefile('simstring')

