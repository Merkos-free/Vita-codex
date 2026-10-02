#include "microphone.hpp"
#include <psp2/audioin.h>
#include <psp2/kernel/processmgr.h>
#include <algorithm>
#include <cmath>

MicrophoneProbe::~MicrophoneProbe() {stop();}
bool MicrophoneProbe::start() {
    stop(); error_=0;
    port_=sceAudioInOpenPort(SCE_AUDIO_IN_PORT_TYPE_VOICE,256,16000,SCE_AUDIO_IN_PARAM_FORMAT_S16_MONO);
    if (port_<0) {error_=port_; port_=-1; return false;}
    started_=last_tick_=sceKernelGetProcessTimeWide();
    return true;
}
void MicrophoneProbe::tick() {
    if (port_<0) return;
    const uint64_t now=sceKernelGetProcessTimeWide();
    // Fail closed on a clock reset, ten elapsed seconds or a long frame gap.
    // Power callbacks also stop the probe; it never restarts automatically.
    if (now<last_tick_ || now-started_>=10000000 || now-last_tick_>=500000) {
        stop(); return;
    }
    last_tick_=now;
    int16_t frame[256]{};
    const int result=sceAudioInInput(port_,frame); // one 16 ms block
    float energy=0;
    if (result>=0) for (auto value:frame) energy+=float(value)*float(value);
    // Volatile stores prevent an optimiser from removing the buffer wipe.
    volatile int16_t* wipe=frame;
    for (size_t i=0;i<256;++i) wipe[i]=0;
    if (result<0) {error_=result; stop(); return;}
    const uint64_t end=sceKernelGetProcessTimeWide();
    if (end<now || end-started_>=10000000 || end-now>=500000) {stop(); return;}
    seconds_=float(end-started_)/1000000.0f;
    level_=std::min(1.0f,std::sqrt(energy/256.0f)/12000.0f);
}
void MicrophoneProbe::stop() {
    if (port_>=0) sceAudioInReleasePort(port_);
    port_=-1; level_=0; seconds_=0; started_=last_tick_=0;
}
