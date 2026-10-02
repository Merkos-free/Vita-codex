#include "../client/src/ime_text.hpp"
#include "../client/src/ui_model.hpp"
#include "../client/src/microphone.hpp"
#include <cassert>
#include <iostream>
namespace {
uint64_t now=0, delay=16000;
int opens=0, captures=0, releases=0, open_result=128, input_result=0;
}
uint64_t sceKernelGetProcessTimeWide() {return now;}
int sceAudioInOpenPort(int,int grain,int rate,int) {
    assert(grain==256 && rate==16000); ++opens; return open_result;
}
int sceAudioInInput(int,void* data) {
    ++captures; now+=delay;
    auto p=static_cast<int16_t*>(data);
    for(int i=0;i<256;++i) p[i]=6000;
    return input_result;
}
int sceAudioInReleasePort(int) {++releases; return 0;}
int main() {
    int checks=0;
    auto roundtrip=[](const std::string& s,size_t limit) {
        auto data=cv::to_ime(s,limit);
        assert(!data.empty() && data.back()==0 && data.size()<=limit+1);
        return cv::utf16_to_utf8(data.data(),data.size());
    };
    assert(roundtrip("Русский текст / src/rpc.ts",2048)=="Русский текст / src/rpc.ts"); ++checks;
    assert(roundtrip("\xF0\x9F\x98\x80",2)=="\xF0\x9F\x98\x80"); ++checks;
    assert(roundtrip("\xF0\x9F\x98\x80",1).empty()); ++checks;
    assert(roundtrip("abc",0).empty()); ++checks;
    assert(roundtrip("abc",2)=="ab"); ++checks;
    assert(roundtrip(std::string("a\0b",3),9)=="a"); ++checks;
    assert(roundtrip("\xFF",9)=="\xEF\xBF\xBD"); ++checks;
    assert(roundtrip("\xC0\xAF",9).find('/')==std::string::npos); ++checks;
    assert(roundtrip("\xED\xA0\x80",9).find("\xED\xA0\x80")==std::string::npos); ++checks;
    assert(roundtrip("\xF4\x90\x80\x80",9).find("\xF4\x90\x80\x80")==std::string::npos); ++checks;
    assert(roundtrip("\xE2\x82",9)=="\xEF\xBF\xBD\xEF\xBF\xBD"); ++checks;
    for(int b=1;b<256;++b) {auto v=cv::to_ime(std::string(1,char(b)),1); assert(v.size()<=2 && v.back()==0);} ++checks;
    MicrophoneProbe mic;
    assert(mic.start() && mic.active()); ++checks;
    mic.tick(); assert(mic.level()>0 && mic.seconds()>0); ++checks;
    mic.stop(); assert(!mic.active() && mic.level()==0 && releases==1); ++checks;
    const auto cap=captures; mic.tick(); assert(captures==cap); ++checks;
    mic.start(); now+=500001; mic.tick(); assert(!mic.active() && captures==cap); ++checks;
    now=100000; mic.start(); now=1; mic.tick(); assert(!mic.active()); ++checks;
    now=0; mic.start();
    while(mic.active() && now<11000000) {mic.tick(); now+=16000;}
    assert(!mic.active() && now>=10000000 && now<=10048000); ++checks;
    open_result=-123; assert(!mic.start() && mic.error()==-123); ++checks;
    open_result=128; input_result=-42; mic.start(); mic.tick();
    assert(!mic.active() && mic.error()==-42); ++checks;
    input_result=0; delay=600000; mic.start(); mic.tick(); assert(!mic.active()); ++checks;
    delay=16000;
    const auto before=releases; {MicrophoneProbe other; other.start();}
    assert(releases==before+1); ++checks;
    std::cout<<checks<<" native-input checks passed (SDK doubles; NOT hardware).\n";
}
