#include "../client/shared/ui.hpp"
#include <cassert>
#include <iostream>

static const std::string patch=
    "diff --git a/example.ts b/example.ts\n--- a/example.ts\n+++ b/example.ts\n"
    "@@ -1,2 +1,2 @@\n const value = 'данные';\n-const balance = Number(value);\n+const balance = BigInt(value);\n"
    "diff --git a/tests/check.ts b/tests/check.ts\nnew file mode 100644\n--- /dev/null\n+++ b/tests/check.ts\n"
    "@@ -0,0 +1 @@\n+expect(balance).toBe(42n);\n";
static float measure(const std::string& t,int size){size_t n=0;for(unsigned char c:t)if((c&0xc0)!=0x80)++n;return float(n)*size*0.65f;}
static const cv::Button& button(const cv::Scene& scene,cv::Command command){for(const auto& b:scene.buttons)if(b.command==command)return b;throw std::runtime_error("missing test button");}
int main(){
    unsigned checks=0;auto check=[&](bool yes){if(!yes)std::cerr<<"Failed check "<<checks+1<<'\n';assert(yes);++checks;};
    cv::DiffIndex d(patch);check(d.files.size()==2);check(d.files[0].name=="example.ts");check(d.files[0].added==1&&d.files[0].removed==1);check(!d.files[0].partial&&!d.truncated);check(d.files[1].name=="tests/check.ts"&&d.files[1].added==1);
    check(d.matching("BigInt")==std::vector<size_t>{0});check(d.matching("tests/")==std::vector<size_t>{1});check(d.matching("balance").size()==2);check(d.matching("not-found").empty());check(d.matching("").size()==2);
    check(cv::patch_path("\"b/\\320\\270\\320\\274\\321\\217.txt\"")=="имя.txt");check(cv::patch_path("b/a path.ts\t2026-01-01")=="a path.ts");
    check(cv::patch_path("\"b/with\\tcontrol\"")=="with\\x09control");check(cv::patch_path("rename/path",false)=="rename/path");
    check(cv::patch_path("\"b/\\777\"")=="\"b/\\777\"");check(cv::patch_path("\"b/\\377\"")=="\"b/\\377\"");check(cv::patch_path("/dev/null")=="/dev/null");
    check(cv::git_header_path("diff --git a/my file.ts b/my file.ts")=="my file.ts");
    check(cv::git_header_path("diff --git \"a/old\\tname\" \"b/new\\tname\"")=="new\\x09name");
    cv::DiffIndex deletion("diff --git a/remove.ts b/remove.ts\n--- a/remove.ts\n+++ /dev/null\n@@ -1 +0,0 @@\n-old\n");check(deletion.files[0].name=="remove.ts"&&deletion.files[0].removed==1);
    cv::DiffIndex renamed("diff --git a/old name b/new name\nsimilarity index 100%\nrename from old name\nrename to new name\n");check(renamed.files[0].name=="new name");
    cv::DiffIndex binary("diff --git a/image.png b/image.png\nBinary files a/image.png and b/image.png differ\n");check(binary.files[0].binary&&binary.files[0].added==0);
    cv::DiffIndex unified("--- a/one\n+++ b/one\n@@ -1 +1 @@\n-x\n+y\n--- a/two\n+++ b/two\n@@ -1 +1 @@\n-z\n+w\n");check(unified.files.size()==2&&unified.files[1].name=="two");
    cv::DiffIndex markers("--- a/one\n+++ b/one\n@@ -1 +1 @@\n--- not a file\n+++ not a file\n");check(markers.files.size()==1&&markers.files[0].name=="one");check(markers.files[0].added==1&&markers.files[0].removed==1);
    cv::DiffIndex incomplete("--- a/one\n+++ b/one\n@@ -5,2 +5,2 @@\n-a\n+b\n");check(incomplete.files[0].partial);
    cv::DiffIndex malformed("--- a/one\n+++ b/one\n@@ rubbish @@\n+a\n");check(malformed.files[0].partial&&malformed.files[0].added==0);
    cv::DiffIndex metadata("unrecognized patch data\n+not necessarily added\n");check(metadata.files.size()==1&&metadata.files[0].added==0);
    check(cv::DiffIndex().files.empty());check(cv::DiffIndex(patch,true).truncated);
    cv::DiffIndex huge(std::string(cv::DiffIndex::MaxBytes+1,'x'));check(huge.truncated&&huge.files[0].partial);
    std::string many;for(size_t i=0;i<140;++i)many+="diff --git a/f b/f\n";cv::DiffIndex many_files(many);check(many_files.files.size()==128&&many_files.truncated);
    std::string rows;for(size_t i=0;i<9000;++i)rows+="line\n";cv::DiffIndex many_rows(rows);check(many_rows.truncated&&many_rows.files[0].rows.size()==8192);
    check(cv::display_safe("a\tb\r\x1b")=="a\\x09b\\x0D\\x1B");
    size_t old=0,fresh=0;check(cv::hunk_counts("@@ -12,0 +1,2 @@ name",old,fresh)&&old==0&&fresh==2);check(!cv::hunk_counts("@@ -99999999999999999999 +1 @@",old,fresh));
    // Shared UI, not SDK substitutes: no network or model is invoked by this test.
    cv::Session s;cv::Ui ui;s.project="test";s.thread="thread";s.view=cv::Json::obj({{"diff",cv::Json(patch)}});
    ui.jump(cv::Page::Files);auto scene=ui.draw(s,measure);check(ui.diff.files.size()==2&&!ui.file_open);
    check(scene.buttons.size()==5);auto old_button=button(scene,cv::Command::Search);
    ui.activate(s,button(scene,cv::Command::File));scene=ui.draw(s,measure);check(ui.file_open&&ui.file_selected==0);
    ui.activate(s,button(scene,cv::Command::NextFile));scene=ui.draw(s,measure);check(ui.file_selected==1);check(!button(scene,cv::Command::NextFile).enabled);
    ui.back();scene=ui.draw(s,measure);check(!ui.file_open&&ui.page==cv::Page::Files);
    ui.apply_text(s,cv::Input::Search,"BigInt");scene=ui.draw(s,measure);check(scene.buttons.size()==4);check(ui.query=="BigInt");
    ui.activate(s,button(scene,cv::Command::File));scene=ui.draw(s,measure);check(ui.file_open&&ui.file_selected==0);
    bool highlighted=false;for(const auto& p:scene.panels)if(p.second==0x35435a)highlighted=true;check(highlighted);
    ui.apply_text(s,cv::Input::Search,"no match");scene=ui.draw(s,measure);check(!ui.file_open&&scene.buttons.size()==3);
    ui.apply_text(s,cv::Input::Search,"x\ny");check(ui.query=="no match");ui.apply_text(s,cv::Input::Search,std::string(129,'x'));check(ui.query=="no match");
    ui.activate(s,button(scene,cv::Command::ClearSearch));scene=ui.draw(s,measure);check(ui.query.empty()&&scene.buttons.size()==5);
    ui.jump(cv::Page::Chat);scene=ui.draw(s,measure);auto edit=button(scene,cv::Command::Edit);check(ui.activate(s,edit)==cv::Input::Draft);
    ui.jump(cv::Page::Settings);check(ui.activate(s,edit)==cv::Input::None);ui.jump(cv::Page::Files);check(ui.activate(s,old_button)==cv::Input::None);
    scene=ui.draw(s,measure);ui.tap(s,scene,30,70);check(ui.page==cv::Page::Projects); // tab, not the old file button
    ui.jump(cv::Page::Files);ui.draw(s,measure);ui.apply_text(s,cv::Input::Search,"balance");s.thread="other";ui.draw(s,measure);check(ui.query.empty()&&!ui.file_open);
    s.view=cv::Json::obj();scene=ui.draw(s,measure);check(ui.diff.files.empty());check(!button(scene,cv::Command::Search).enabled);
    // Search stays functional when a hit spans wrapped display rows; cycling wraps.
    std::string body="--- a/long.txt\n+++ b/long.txt\n@@ -0,0 +1,25 @@\n";
    for(int n=0;n<25;++n)body+="+"+(n==0||n==24?std::string("balance"):std::string("plain"))+"\n";
    s.view=cv::Json::obj({{"diff",cv::Json(body)}});scene=ui.draw(s,measure);ui.activate(s,button(scene,cv::Command::File));
    ui.apply_text(s,cv::Input::Search,"balance");scene=ui.draw(s,measure);ui.activate(s,button(scene,cv::Command::NextMatch));const int first_hit=ui.scroll;
    scene=ui.draw(s,measure);ui.activate(s,button(scene,cv::Command::NextMatch));check(ui.scroll>first_hit);
    scene=ui.draw(s,measure);ui.activate(s,button(scene,cv::Command::NextMatch));check(ui.scroll==first_hit);
    // Changed snapshots and navigation invalidate buttons from the previous render.
    const auto prior_search=button(scene,cv::Command::Search);
    s.view.object["diff"]=cv::Json(patch);ui.draw(s,measure);check(ui.activate(s,prior_search)==cv::Input::None);
    // Deterministic malformed-input corpus under ASan/UBSan, no external processes.
    uint32_t seed=0x56ac12u;
    for(int sample=0;sample<250;++sample){std::string noise="--- a/f\n+++ b/f\n";
        for(int n=0;n<512;++n){seed=1664525u*seed+1013904223u;noise+=char(seed>>24);}
        cv::DiffIndex parsed(noise);assert(parsed.files.size()<=cv::DiffIndex::MaxFiles);
        for(const auto& f:parsed.files){assert(cv::valid_utf8(f.name));for(const auto& row:f.rows)assert(cv::valid_utf8(row.text));}
    }
    // Long labels and titles remain inside 960x544, at realistic worst-case metrics.
    s.project=std::string(300,'p');s.notice=std::string(2000,'n');s.ready=true;
    s.projects={cv::Json::obj({{"name",cv::Json(std::string(4000,'n'))},{"id",cv::Json("test")}})};
    for(int page=0;page<6;++page){ui.jump(static_cast<cv::Page>(page));scene=ui.draw(s,measure);
        for(const auto& t:scene.text){check(t.x>=0&&t.y<=544&&t.x+measure(t.value,t.size)<=944.1f);}
        for(const auto& b:scene.buttons){check(b.rect.x>=0&&b.rect.y>=0&&b.rect.x+b.rect.w<=960&&b.rect.y+b.rect.h<=544);check(measure(b.title,18)<=b.rect.w-24+0.1f);}
    }
    // Permission UI: a stale scene cannot approve a replacement ticket/details.
    s.stale=false;s.view=cv::Json::obj({{"approvals",cv::Json::list({cv::Json::obj({{"id",cv::Json("ticket")},{"details",cv::Json("short")}})})}});
    ui.jump(cv::Page::Approvals);scene=ui.draw(s,measure);auto allow=button(scene,cv::Command::Allow);check(allow.enabled);check(ui.activate(s,allow)==cv::Input::None);
    ui.hold.select_accept(true);ui.hold.update(true,100);s.view.object["approvals"].array[0].object["details"]=cv::Json("replacement");ui.draw(s,measure);check(ui.hold.held_ms==0);check(ui.activate(s,allow,true)==cv::Input::None);
    s.view.object["approvals"].array[0].object["details"]=cv::Json(std::string(20000,'x'));scene=ui.draw(s,measure);check(!button(scene,cv::Command::Allow).enabled&&ui.max_scroll>0);
    ui.scroll=ui.max_scroll;scene=ui.draw(s,measure);check(button(scene,cv::Command::Allow).enabled);
    ui.hold.select_accept(true);ui.hold.update(true,100);ui.focus_by(1,scene.buttons.size());check(ui.hold.held_ms==0);
    s.stale=true;scene=ui.draw(s,measure);check(!button(scene,cv::Command::Allow).enabled);
    std::cout<<checks<<" diff/parser/navigation/layout checks + 250 malformed-input samples passed (host, no account/device)\n";
}
