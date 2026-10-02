#pragma once
#include <cstdint>
#include <vector>

// Local hardware probe only. Audio stays in RAM, is never uploaded or written to disk.
class MicrophoneProbe {
    int port_=-1;
    std::vector<int16_t> samples_;
    float level_=0;
    int error_=0;
public:
    ~MicrophoneProbe();
    bool start();
    void tick();
    void stop();
    bool active() const { return port_>=0; }
    float seconds() const { return samples_.size()/16000.0f; }
    float level() const { return level_; }
    int error() const { return error_; }
};
