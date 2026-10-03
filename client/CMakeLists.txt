cmake_minimum_required(VERSION 3.16)
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(DEFINED ENV{VITASDK})
    set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "VitaSDK toolchain")
  else()
    message(FATAL_ERROR "VITASDK is not set. Install VitaSDK or use the pinned CI build image.")
  endif()
endif()
project(codex_vita_ui LANGUAGES C CXX)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_executable(codex_vita_ui src/main.cpp src/microphone.cpp shared/https.cpp)
target_compile_options(codex_vita_ui PRIVATE -Wall -Wextra -Werror -finput-charset=UTF-8)
set(CV_CURL_LIBRARY curl)
if(DEFINED CV_NETWORK_PREFIX)
  set(CV_CURL_LIBRARY "${CV_NETWORK_PREFIX}/lib/libcurl.a")
  target_include_directories(codex_vita_ui BEFORE PRIVATE "${CV_NETWORK_PREFIX}/include")
endif()
target_link_libraries(codex_vita_ui
  -Wl,--start-group vita2d png jpeg ${CV_CURL_LIBRARY} ssl crypto zstd z m stdc++ pthread -Wl,--end-group
  SceDisplay_stub SceGxm_stub SceSysmodule_stub SceCtrl_stub SceTouch_stub
  ScePgf_stub ScePvf_stub SceCommonDialog_stub SceIme_stub SceAppUtil_stub SceAppMgr_stub
  SceNet_stub SceNetCtl_stub SceHttp_stub SceSsl_stub SceIofilemgr_stub
  ScePower_stub SceAudioIn_stub SceKernelThreadMgr_stub SceLibKernel_stub)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(ASSET_DIR "${CMAKE_CURRENT_BINARY_DIR}/assets")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/make_vita_assets.py")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/make_vita_assets.py" "${ASSET_DIR}" RESULT_VARIABLE ASSET_RESULT)
if(NOT ASSET_RESULT EQUAL 0)
  message(FATAL_ERROR "Original LiveArea asset generation failed")
endif()
vita_create_self(codex_vita_ui.self codex_vita_ui)
# Deliberately named UI prototype, not a working Codex client.
# Title ID is provisional; check for collision before device installation.
vita_create_vpk(codex-vita-ui-prototype.vpk CVITA0001 codex_vita_ui.self
  VERSION 00.21 NAME "Codex Vita Test"
  FILE "${ASSET_DIR}/icon0.png" "sce_sys/icon0.png"
  FILE "${ASSET_DIR}/bg.png" "sce_sys/livearea/contents/bg.png"
  FILE "${ASSET_DIR}/startup.png" "sce_sys/livearea/contents/startup.png"
  FILE "${ASSET_DIR}/template.xml" "sce_sys/livearea/contents/template.xml")
