#include "../client/src/ui_model.hpp"
#include <cassert>
#include <iostream>
int main() {
    int checks=0;
    for(int i=0;i<cv::screen_count;++i) {
        auto r=cv::tab_rect(i);
        assert(r.x>=0 && r.y>=0 && r.x+r.w<=cv::width && r.y+r.h<=cv::height); ++checks;
        assert(cv::inside(r,r.x,r.y) && !cv::inside(r,r.x+r.w,r.y)); ++checks;
        if(i) {auto prev=cv::tab_rect(i-1); assert(prev.x+prev.w<r.x); ++checks;}
    }
    cv::Model m; m.navigate(-1); assert(m.screen==cv::Screen::Settings); ++checks;
    m.navigate(1); assert(m.screen==cv::Screen::Overview); ++checks;
    m.select(200); assert(m.screen==cv::Screen::Overview); ++checks;
    m.scroll_by(100,60); assert(m.scroll==60); ++checks;
    m.scroll_by(-100,60); assert(m.scroll==0); ++checks;
    assert(!m.connected); ++checks;
    uint16_t s[]={0x041F,0x0440,0x0438,0x0432,0x0435,0x0442,0};
    assert(cv::utf16_to_utf8(s,7)=="Привет"); ++checks;
    uint16_t surrogate[]={0xD83D,0xDE00,0};
    assert(cv::utf16_to_utf8(surrogate,3)=="\xF0\x9F\x98\x80"); ++checks;
    uint16_t broken[]={0xD800,0};
    assert(cv::utf16_to_utf8(broken,2)=="\xEF\xBF\xBD"); ++checks;
    auto byte_width=[](const std::string& str){return float(str.size());};
    auto lines=cv::wrap("longunbrokenfilepath",4,byte_width);
    for(const auto& line:lines) {assert(line.size()<=4); ++checks;}
    lines=cv::wrap("Привет",4,byte_width);
    assert(lines.size()==3 && lines[0]=="Пр" && lines[2]=="ет"); ++checks;
    lines=cv::wrap("a\nb\n\nc",20,byte_width);
    assert(lines.size()==4 && lines[2].empty()); ++checks;
    cv::ApprovalHold hold;
    assert(!hold.update(true,5000)); ++checks;
    hold.select_accept(true); assert(!hold.update(true,5000)); ++checks;
    for(int i=0;i<13;++i) assert(!hold.update(true,100));
    assert(hold.update(true,100)); ++checks;
    assert(!hold.update(true,100)); ++checks;
    hold.select_accept(true); hold.update(true,100); hold.update(false,100);
    assert(hold.held_ms==0); ++checks;
    std::cout<<checks<<" grouped checks passed; host model only, not Vita rendering.\n";
}
