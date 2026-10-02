#pragma once
#include <cstdint>

// Local meter only: no recording history, disk I/O, network or transcription.
class MicrophoneProbe {
    int port_=-1;
    uint64_t started_=0, last_tick_=0;
    float level_=0, seconds_=0;
    int error_=0;
public:
    MicrophoneProbe()=default;
    MicrophoneProbe(const MicrophoneProbe&)=delete;
    MicrophoneProbe& operator=(const MicrophoneProbe&)=delete;
    ~MicrophoneProbe();
    bool start();
    void tick();
    void stop();
    bool active() const { return port_>=0; }
    float seconds() const { return seconds_; }
    float level() const { return level_; }
    int error() const { return error_; }
};
