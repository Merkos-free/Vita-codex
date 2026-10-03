#pragma once
// Read-only, bounded index of a received patch. Never opens paths or applies edits.
#include "json.hpp"
#include <algorithm>
#include <cstdint>
#include <string>
#include <vector>

namespace cv {
enum class DiffKind { Meta, Context, Add, Remove, Hunk };
struct DiffRow {std::string text; DiffKind kind=DiffKind::Meta;};
struct DiffFile {
    std::string name="Неопределённый файл";
    std::vector<DiffRow> rows;
    size_t added=0,removed=0;
    bool binary=false,partial=false;
};
inline std::string display_safe(const std::string& value) {
    // Preserve Unicode but render control bytes literally, not as layout commands.
    if(!valid_utf8(value))return "[некорректный UTF-8]";
    static const char* hex="0123456789ABCDEF";
    std::string out;
    for(unsigned char c:value){if(c<32||c==127){out+="\\x";out+=hex[c>>4];out+=hex[c&15];}else out+=char(c);}
    return out;
}
inline std::string patch_path(std::string value,bool prefix=true) {
    // Git C-quoted paths use octal bytes; unified diff may have a tab timestamp.
    if(!value.empty()&&value[0]=='"'){
        std::string decoded; bool closed=false;
        for(size_t i=1;i<value.size();++i){
            char c=value[i];
            if(c=='"'){if(i+1!=value.size())return display_safe(value);closed=true;break;}
            if(c!='\\'){decoded+=c;continue;}
            if(++i>=value.size())return display_safe(value);
            c=value[i];
            if(c>='0'&&c<='7'){
                unsigned byte=unsigned(c-'0');int n=1;
                while(n<3&&i+1<value.size()&&value[i+1]>='0'&&value[i+1]<='7'){byte=byte*8+unsigned(value[++i]-'0');++n;}
                if(byte>255)return display_safe(value);
                decoded+=char(byte);
            }else if(c=='t')decoded+='\t';else if(c=='n')decoded+='\n';else if(c=='r')decoded+='\r';
            else if(c=='b')decoded+='\b';else if(c=='f')decoded+='\f';else if(c=='v')decoded+='\v';else if(c=='a')decoded+='\a';
            else if(c=='\\'||c=='"')decoded+=c;else return display_safe(value);
        }
        if(!closed||!valid_utf8(decoded))return display_safe(value);
        value=std::move(decoded);
    }else{auto tab=value.find('\t');if(tab!=std::string::npos)value.resize(tab);}
    if(prefix&&(value.compare(0,2,"a/")==0||value.compare(0,2,"b/")==0))value.erase(0,2);
    return display_safe(value);
}
inline std::string git_header_path(const std::string& header) {
    const auto v=header.substr(11); // after "diff --git "
    if(v.empty())return "Неопределённый файл";
    // Quoted first path: find its closing quote, skipping escaped bytes.
    if(v[0]=='"'){
        size_t i=1;for(;i<v.size();++i){if(v[i]=='\\'&&i+1<v.size())++i;else if(v[i]=='"')break;}
        if(i+2<v.size()&&v[i+1]==' ')return patch_path(v.substr(i+2));
    }
    // An unchanged name containing spaces is emitted without quotes by Git.
    for(size_t i=v.find(" b/");i!=std::string::npos;i=v.find(" b/",i+1))
        if(v.compare(0,2,"a/")==0&&v.substr(2,i-2)==v.substr(i+3))return patch_path(v.substr(i+1));
    auto split=v.find(' ');
    if(split!=std::string::npos&&v.find(' ',split+1)==std::string::npos)return patch_path(v.substr(split+1));
    // Extended rename/---/+++ headers will provide an unambiguous name later.
    return "Имя — в заголовке изменения";
}
inline bool hunk_counts(const std::string& line,size_t& old_left,size_t& new_left) {
    size_t i=0;
    auto literal=[&](const char* s){for(;*s;++s)if(i>=line.size()||line[i++]!=*s)return false;return true;};
    auto number=[&](size_t& n){n=0;size_t start=i;while(i<line.size()&&line[i]>='0'&&line[i]<='9'){if(n>100000000)return false;n=n*10+size_t(line[i++]-'0');}return i>start;};
    auto range=[&](size_t& count){size_t start=0;if(!number(start))return false;count=1;if(i<line.size()&&line[i]==','){++i;return number(count);}return true;};
    return literal("@@ -")&&range(old_left)&&literal(" +")&&range(new_left)&&literal(" @@");
}
struct DiffIndex {
    static constexpr size_t MaxBytes=256*1024,MaxRows=8192,MaxFiles=128;
    std::vector<DiffFile> files;
    bool truncated=false;
    explicit DiffIndex(const std::string& patch="",bool upstream_truncated=false){parse(patch,upstream_truncated);}
    void parse(const std::string& patch,bool upstream_truncated=false){
        files.clear();truncated=upstream_truncated||patch.size()>MaxBytes;
        size_t length=std::min(patch.size(),MaxBytes),pos=0,total=0,old_left=0,new_left=0;
        bool in_hunk=false,git_section=false;
        auto start_file=[&](){if(in_hunk&&(old_left||new_left)&&!files.empty())files.back().partial=true;in_hunk=false;old_left=new_left=0;if(files.size()>=MaxFiles){truncated=true;return false;}files.emplace_back();return true;};
        while(pos<length){
            if(total++>=MaxRows){truncated=true;break;}
            size_t end=patch.find('\n',pos);if(end==std::string::npos||end>length)end=length;
            std::string line=patch.substr(pos,end-pos);pos=end<length?end+1:length;
            if(!line.empty()&&line.back()=='\r')line.pop_back();
            if(line.compare(0,11,"diff --git ")==0){if(!start_file())break;git_section=true;files.back().name=git_header_path(line);}
            else if(line.compare(0,10,"diff --cc ")==0||line.compare(0,16,"diff --combined ")==0){if(!start_file())break;git_section=true;files.back().name="Combined diff (исходный текст)";files.back().partial=true;}
            else if(line.compare(0,4,"--- ")==0&&!in_hunk){
                if(files.empty()||(!git_section&&!files.back().rows.empty())){if(!start_file())break;}
                files.back().name=patch_path(line.substr(4));
            }
            if(files.empty()){if(!start_file())break;}
            auto& file=files.back();DiffKind kind=DiffKind::Meta;
            if(!in_hunk&&line.compare(0,4,"+++ ")==0&&line.substr(4)!="/dev/null")file.name=patch_path(line.substr(4));
            if(line.compare(0,10,"rename to ")==0)file.name=patch_path(line.substr(10),false);
            if(line.compare(0,8,"copy to ")==0)file.name=patch_path(line.substr(8),false);
            if(line.compare(0,13,"Binary files ")==0||line=="GIT binary patch")file.binary=true;
            if(line.compare(0,3,"@@ ")==0){
                if(in_hunk&&(old_left||new_left))file.partial=true;
                in_hunk=hunk_counts(line,old_left,new_left);kind=DiffKind::Hunk;
                if(!in_hunk)file.partial=true;
            }else if(in_hunk){
                if(!line.empty()&&line[0]=='+'&&new_left){kind=DiffKind::Add;--new_left;++file.added;}
                else if(!line.empty()&&line[0]=='-'&&old_left){kind=DiffKind::Remove;--old_left;++file.removed;}
                else if(!line.empty()&&line[0]==' '&&old_left&&new_left){kind=DiffKind::Context;--old_left;--new_left;}
                else if(line!="\\ No newline at end of file"){file.partial=true;in_hunk=false;}
            }
            file.rows.push_back({display_safe(line),kind});
            if(in_hunk&&!old_left&&!new_left)in_hunk=false;
        }
        if(!files.empty()&&((in_hunk&&(old_left||new_left))||truncated))files.back().partial=true;
    }
    std::vector<size_t> matching(const std::string& query)const{
        std::vector<size_t> result;
        for(size_t i=0;i<files.size();++i){bool yes=query.empty()||files[i].name.find(query)!=std::string::npos;
            if(!yes)for(const auto& row:files[i].rows)if(row.text.find(query)!=std::string::npos){yes=true;break;}
            if(yes)result.push_back(i);
        }return result;
    }
};
} // namespace cv
