#pragma once
// Test double declarations only. Never on the Vita build include path.
constexpr int SCE_AUDIO_IN_PORT_TYPE_VOICE=0;
constexpr int SCE_AUDIO_IN_PARAM_FORMAT_S16_MONO=0;
int sceAudioInOpenPort(int,int,int,int);
int sceAudioInInput(int,void*);
int sceAudioInReleasePort(int);
