cmake_minimum_required(VERSION 3.21)

project({{ID}} VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED YES)

include(FetchContent)
option(RED4EXT_INSTALL "" OFF)
option(RED4EXT_USE_PCH "" ON)

# Pinned to the RED4ext.SDK commit that added game 2.5 (runtime 3.0.88.46235).
# Tag 1.0.0 still declares 2.31 as the latest runtime, and RED4ext refuses a
# plugin built for another runtime. Move this pin only after a test build.
FetchContent_Declare(
  RED4ext.SDK
  GIT_REPOSITORY https://github.com/WopsS/RED4ext.SDK.git
  GIT_TAG        0f5eba42a4cf3a1161ad3de0b4ed6f1901ec169e
)
FetchContent_MakeAvailable(RED4ext.SDK)

add_library(${PROJECT_NAME} SHARED src/Main.cpp)
target_link_libraries(${PROJECT_NAME} PRIVATE RED4ext::SDK)
target_compile_definitions(${PROJECT_NAME} PRIVATE
  PLUGIN_VERSION_MAJOR=${PROJECT_VERSION_MAJOR}
  PLUGIN_VERSION_MINOR=${PROJECT_VERSION_MINOR}
  PLUGIN_VERSION_PATCH=${PROJECT_VERSION_PATCH})
