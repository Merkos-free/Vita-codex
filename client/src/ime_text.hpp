#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace cv {
// Bounded UTF-8 -> Vita's uint16_t IME buffer. Always NUL-terminated.
// Invalid sequences become U+FFFD; never cut a surrogate pair at capacity.
inline std::vector<uint16_t> to_ime(const std::string& text, size_t max_units) {
    std::vector<uint16_t> out;
    out.reserve(max_units < text.size() ? max_units + 1 : text.size() + 1);
    for (size_t i=0; i<text.size();) {
        const auto lead=static_cast<unsigned char>(text[i]);
        uint32_t cp=0xFFFD; size_t count=1;
        if (lead<0x80) cp=lead;
        else {
            const size_t n=(lead>=0xC2 && lead<=0xDF)?2:
                (lead>=0xE0 && lead<=0xEF)?3:(lead>=0xF0 && lead<=0xF4)?4:0;
            if (n && n<=text.size()-i) {
                uint32_t value=lead & ((1u<<(7-n))-1u);
                bool valid=true;
                for (size_t j=1;j<n;++j) {
                    const auto b=static_cast<unsigned char>(text[i+j]);
                    if ((b&0xC0)!=0x80) {valid=false; break;}
                    value=(value<<6)|(b&0x3F);
                }
                const uint32_t minimum=n==2?0x80:n==3?0x800:0x10000;
                if (valid && value>=minimum && value<=0x10FFFF && !(value>=0xD800 && value<=0xDFFF)) {
                    cp=value; count=n;
                }
            }
        }
        i+=count;
        if (!cp) break;
        const size_t need=cp>0xFFFF?2:1;
        if (need>max_units-out.size()) break;
        if (need==1) out.push_back(static_cast<uint16_t>(cp));
        else {
            cp-=0x10000;
            out.push_back(static_cast<uint16_t>(0xD800+(cp>>10)));
            out.push_back(static_cast<uint16_t>(0xDC00+(cp&0x3FF)));
        }
    }
    out.push_back(0);
    return out;
}
} // namespace cv
