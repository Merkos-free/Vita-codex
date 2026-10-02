#pragma once
// Small bounded JSON value for the bridge protocol. No executable configuration.
#include <cctype>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace cv {
struct Json {
    enum class Type { Null, Bool, Number, String, Array, Object } type=Type::Null;
    std::string scalar;
    std::vector<Json> array;
    std::map<std::string,Json> object;
    Json()=default;
    explicit Json(const std::string& s):type(Type::String),scalar(s){}
    explicit Json(const char* s):Json(std::string(s)){}
    static Json obj(std::map<std::string,Json> v={}) {Json j;j.type=Type::Object;j.object=std::move(v);return j;}
    static Json list(std::vector<Json> v={}) {Json j;j.type=Type::Array;j.array=std::move(v);return j;}
    static Json boolean(bool v) {Json j;j.type=Type::Bool;j.scalar=v?"true":"false";return j;}
    const Json& at(const std::string& key) const {
        static const Json empty;
        auto it=object.find(key); return it==object.end()?empty:it->second;
    }
    std::string str(const std::string& fallback="") const {return type==Type::String?scalar:fallback;}
    bool yes() const {return type==Type::Bool && scalar=="true";}
    static std::string quote(const std::string& s) {
        std::string out="\""; const char* hex="0123456789abcdef";
        for(unsigned char c:s) {
            if(c=='"'||c=='\\') {out+='\\';out+=static_cast<char>(c);}
            else if(c<32) {out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}
            else out+=static_cast<char>(c);
        }
        return out+'"';
    }
    std::string dump() const {
        switch(type) {
        case Type::Null:return "null";
        case Type::Bool:case Type::Number:return scalar;
        case Type::String:return quote(scalar);
        case Type::Array: {std::string s="[";for(const auto& x:array){if(s.size()>1)s+=',';s+=x.dump();}return s+']';}
        case Type::Object: {std::string s="{";for(const auto& x:object){if(s.size()>1)s+=',';s+=quote(x.first)+':'+x.second.dump();}return s+'}';}
        }
        throw std::runtime_error("JSON type");
    }
};

inline bool valid_utf8(const std::string& s) {
    for(size_t i=0;i<s.size();) {
        unsigned char c=s[i++]; if(c<128) {if(!c)return false;continue;}
        unsigned n=0;uint32_t cp=0,minimum=0;
        if(c>=0xC2&&c<=0xDF){n=1;cp=c&31;minimum=0x80;}
        else if(c>=0xE0&&c<=0xEF){n=2;cp=c&15;minimum=0x800;}
        else if(c>=0xF0&&c<=0xF4){n=3;cp=c&7;minimum=0x10000;}
        else return false;
        if(n>s.size()-i)return false;
        while(n--) {unsigned char b=s[i++];if((b&0xC0)!=0x80)return false;cp=(cp<<6)|(b&63);}
        if(cp<minimum||cp>0x10FFFF||(cp>=0xD800&&cp<=0xDFFF))return false;
    }
    return true;
}

class JsonReader {
    const std::string& s; size_t p=0,nodes=0;
    [[noreturn]] void fail() const {throw std::runtime_error("Invalid or oversized JSON response");}
    void ws(){while(p<s.size()&&(s[p]==' '||s[p]=='\r'||s[p]=='\n'||s[p]=='\t'))++p;}
    bool take(char c){ws();if(p<s.size()&&s[p]==c){++p;return true;}return false;}
    uint32_t hex4(){uint32_t v=0;for(int i=0;i<4;++i){if(p>=s.size())fail();char c=s[p++];v<<=4;
        if(c>='0'&&c<='9')v+=c-'0';else if(c>='a'&&c<='f')v+=c-'a'+10;else if(c>='A'&&c<='F')v+=c-'A'+10;else fail();}return v;}
    static void utf8(std::string& out,uint32_t c) {
        if(c<128)out+=static_cast<char>(c);
        else if(c<2048){out+=static_cast<char>(192|(c>>6));out+=static_cast<char>(128|(c&63));}
        else if(c<65536){out+=static_cast<char>(224|(c>>12));out+=static_cast<char>(128|((c>>6)&63));out+=static_cast<char>(128|(c&63));}
        else{out+=static_cast<char>(240|(c>>18));out+=static_cast<char>(128|((c>>12)&63));out+=static_cast<char>(128|((c>>6)&63));out+=static_cast<char>(128|(c&63));}
    }
    std::string string() {
        if(!take('"'))fail();
        std::string out;
        while(p<s.size()) {
            unsigned char c=s[p++];
            if(c=='"'){if(!valid_utf8(out))fail();return out;}
            if(c<32)fail();
            if(c!='\\')out+=static_cast<char>(c);
            else {
                if(p>=s.size())fail();
                char e=s[p++];
                switch(e) {
                case '"':case '\\':case '/':out+=e;break;
                case 'n':out+='\n';break;case 'r':out+='\r';break;case 't':out+='\t';break;
                case 'b':out+='\b';break;case 'f':out+='\f';break;
                case 'u': {uint32_t cp=hex4();
                    if(cp>=0xD800&&cp<=0xDBFF){if(p+2>s.size()||s[p++]!='\\'||s[p++]!='u')fail();auto lo=hex4();if(lo<0xDC00||lo>0xDFFF)fail();cp=0x10000+((cp-0xD800)<<10)+(lo-0xDC00);}
                    else if(cp>=0xDC00&&cp<=0xDFFF)fail();
                    if(!cp)fail();
                    utf8(out,cp);break;}
                default:fail();
                }
            }
            if(out.size()>262144)fail();
        }
        fail();
    }
    Json value(unsigned depth) {
        if(depth>24||++nodes>8192)fail();
        ws();if(p>=s.size())fail();
        if(s[p]=='"')return Json(string());
        if(take('{')) {Json j=Json::obj();if(take('}'))return j;do{auto key=string();if(key.size()>256||!take(':')||j.object.count(key))fail();j.object.emplace(key,value(depth+1));}while(take(','));if(!take('}'))fail();return j;}
        if(take('[')){Json j=Json::list();if(take(']'))return j;do{j.array.push_back(value(depth+1));}while(take(','));if(!take(']'))fail();return j;}
        if(s.compare(p,4,"null")==0){p+=4;return Json();}
        if(s.compare(p,4,"true")==0){p+=4;return Json::boolean(true);}
        if(s.compare(p,5,"false")==0){p+=5;return Json::boolean(false);}
        const size_t start=p;
        if(s[p]=='-')++p;
        auto digit=[&]{return p<s.size()&&s[p]>='0'&&s[p]<='9';};
        if(!digit())fail();
        if(s[p]=='0')++p;else while(digit())++p;
        if(p<s.size()&&s[p]=='.'){++p;if(!digit())fail();while(digit())++p;}
        if(p<s.size()&&(s[p]=='e'||s[p]=='E')){++p;if(p<s.size()&&(s[p]=='+'||s[p]=='-'))++p;if(!digit())fail();while(digit())++p;}
        if(p-start>64)fail();
        Json j;j.type=Json::Type::Number;j.scalar=s.substr(start,p-start);return j;
    }
public:
    explicit JsonReader(const std::string& text):s(text){}
    Json read(){if(s.size()>1024*1024)fail();auto j=value(0);ws();if(p!=s.size())fail();return j;}
};
inline Json parse_json(const std::string& s){return JsonReader(s).read();}
} // namespace cv
