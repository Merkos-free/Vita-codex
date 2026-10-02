#pragma once
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace cv {
constexpr int width = 960, height = 544;
struct Rect { int x, y, w, h; };
inline bool inside(Rect r, int x, int y) {
    return x >= r.x && x < r.x+r.w && y >= r.y && y < r.y+r.h;
}
enum class Screen { Overview, Chat, Files, Voice, Settings };
constexpr int screen_count = 5;
constexpr Rect footer{16, 496, 928, 32};
constexpr Rect content{24, 144, 912, 336};
inline Rect tab_rect(int n) { return {24+n*184, 78, 172, 46}; }

// Reject malformed code points when passing between Vita IME and UTF-8 UI.
inline std::string utf16_to_utf8(const uint16_t* text, size_t length) {
    std::string out;
    for (size_t i=0; i<length && text[i]; ++i) {
        uint32_t c=text[i];
        if (c>=0xD800 && c<=0xDBFF) {
            if (i+1<length && text[i+1]>=0xDC00 && text[i+1]<=0xDFFF) {
                c=0x10000+((c-0xD800)<<10)+(text[++i]-0xDC00);
            } else c=0xFFFD;
        } else if (c>=0xDC00 && c<=0xDFFF) c=0xFFFD;
        if (c<0x80) out+=static_cast<char>(c);
        else if (c<0x800) { out+=static_cast<char>(0xC0|(c>>6)); out+=static_cast<char>(0x80|(c&63)); }
        else if (c<0x10000) { out+=static_cast<char>(0xE0|(c>>12)); out+=static_cast<char>(0x80|((c>>6)&63)); out+=static_cast<char>(0x80|(c&63)); }
        else { out+=static_cast<char>(0xF0|(c>>18)); out+=static_cast<char>(0x80|((c>>12)&63)); out+=static_cast<char>(0x80|((c>>6)&63)); out+=static_cast<char>(0x80|(c&63)); }
    }
    return out;
}
// Keep long unbroken paths, Cyrillic and newlines within the available width.
// Measure is supplied by the renderer (system font); tests use a deterministic substitute.
template<class Measure>
std::vector<std::string> wrap(const std::string& text, float max_width, Measure measure) {
    std::vector<std::string> lines;
    std::string line;
    if (max_width<=0) return lines;
    for (size_t i=0; i<text.size();) {
        unsigned char lead=static_cast<unsigned char>(text[i]);
        size_t n=lead<128?1:((lead&0xE0)==0xC0?2:((lead&0xF0)==0xE0?3:((lead&0xF8)==0xF0?4:1)));
        n=std::min(n,text.size()-i);
        std::string cp=text.substr(i,n); i+=n;
        if (cp=="\n") { lines.push_back(line); line.clear(); continue; }
        if (cp=="\r") continue;
        if (!line.empty() && measure(line+cp)>max_width) { lines.push_back(line); line.clear(); }
        line+=cp;
    }
    if (!line.empty() || lines.empty()) lines.push_back(line);
    return lines;
}
struct Model {
    Screen screen=Screen::Overview;
    int scroll=0;
    std::string draft;
    bool connected=false;  // Never set true in the M0 offline renderer.
    void navigate(int step) {
        int n=(static_cast<int>(screen)+step)%screen_count;
        if (n<0) n+=screen_count;
        screen=static_cast<Screen>(n); scroll=0;
    }
    void select(int n) {
        if (n>=0 && n<screen_count) {screen=static_cast<Screen>(n); scroll=0;}
    }
    void scroll_by(int delta,int max_scroll) { scroll=std::clamp(scroll+delta,0,std::max(0,max_scroll)); }
};
// UI-side second confirmation. This does not grant permission on the server.
// A future connected screen must also send the current one-use bridge approval ticket.
struct ApprovalHold {
    bool accept_selected=false;
    unsigned held_ms=0;
    void select_accept(bool yes) { accept_selected=yes; held_ms=0; }
    bool update(bool pressed,unsigned elapsed_ms) {
        if (!accept_selected || !pressed) {held_ms=0; return false;}
        held_ms=std::min(held_ms+std::min(elapsed_ms,100u),1500u);
        if (held_ms<1500) return false;
        held_ms=0; accept_selected=false; return true;
    }
};
} // namespace cv
