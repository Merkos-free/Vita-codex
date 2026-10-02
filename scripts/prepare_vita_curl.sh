#!/bin/sh
# Run in the pinned SDK container AFTER the host fetches a hash-pinned source archive.
# No network, credentials, insecure TLS flags or patches to verification are used.
set -eu
: "${VITASDK:?VITASDK must point to the pinned compiler SDK}"
archive="$PWD/build/deps/curl-8.17.0.tar.gz"
printf '%s  %s\n' e8e74cdeefe5fb78b3ae6e90cd542babf788fa9480029cfcee6fd9ced42b7910 "$archive" | sha256sum -c -
mkdir -p build/deps/src build/network
if [ ! -d build/deps/src/curl-8.17.0 ]; then tar xzf "$archive" -C build/deps/src; fi
# Vita OpenSSL omits UI_OpenSSL. Disable curl engine/provider console UI through
# its upstream compile-time guard; CA, peer and hostname verification stay enabled.
cmake -S build/deps/src/curl-8.17.0 -B build/deps/curl-build \
  -DCMAKE_TOOLCHAIN_FILE="$VITASDK/share/vita.toolchain.cmake" \
  -DCMAKE_C_FLAGS=-DOPENSSL_NO_UI_CONSOLE \
  -DCMAKE_INSTALL_PREFIX="$PWD/build/network" -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_CURL_EXE=OFF -DBUILD_SHARED_LIBS=OFF -DBUILD_TESTING=OFF \
  -DENABLE_IPV6=OFF -DCURL_DISABLE_SOCKETPAIR=ON -DHAVE_FCNTL_O_NONBLOCK=OFF \
  -DENABLE_THREADED_RESOLVER=OFF -DBUILD_LIBCURL_DOCS=OFF -DBUILD_MISC_DOCS=OFF \
  -DENABLE_CURL_MANUAL=OFF -DCURL_USE_LIBPSL=OFF -DCURL_USE_OPENSSL=ON \
  -DCURL_CA_BUNDLE=none -DCURL_CA_PATH=none -DCURL_ZSTD=OFF -DCURL_BROTLI=OFF \
  -DUSE_LIBIDN2=OFF -DUSE_NGHTTP2=OFF
sed -i '/HAVE_PIPE2/d' build/deps/curl-build/lib/curl_config.h
cmake --build build/deps/curl-build --parallel 2
cmake --install build/deps/curl-build
