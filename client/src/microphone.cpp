#include "microphone.hpp"
#include <psp2/audioin.h>
#include <algorithm>
#include <cmath>
#include <iterator>

MicrophoneProbe::~MicrophoneProbe() {stop();}
bool MicrophoneProbe::start() {
    stop(); error_=0; samples_.clear(); samples_.reserve(16000*10);
    port_=sceAudioInOpenPort(SCE_AUDIO_IN_PORT_TYPE_VOICE,256,16000,SCE_AUDIO_IN_PARAM_FORMAT_S16_MONO);
    if (port_<0) {error_=port_; port_=-1; return false;}
    return true;
}
void MicrophoneProbe::tick() {
    if (port_<0) return;
    int16_t frame[256]{};
    int result=sceAudioInInput(port_,frame);
    if (result<0) {error_=result; stop(); return;}
    float energy=0;
    for (auto value:frame) energy+=float(value)*float(value);
    level_=std::min(1.0f,std::sqrt(energy/256.0f)/12000.0f);
    const auto n=std::min<size_t>(256,16000*10-samples_.size());
    samples_.insert(samples_.end(),frame,frame+n);
    if (samples_.size()>=16000*10) stop();
}
void MicrophoneProbe::stop() {
    if (port_>=0) sceAudioInReleasePort(port_);
    port_=-1; level_=0;
    // Erase captured voice. No recognition is claimed by this hardware test.
    std::fill(samples_.begin(),samples_.end(),0);
    samples_.clear();
}
